"""Generative evaluation on the test split: in PyTorch (checkpoint) or through an OpenAI-compatible server.

    printloop-ft evaluate --config configs/train_mi300x.yaml                 # fine-tuned (adapter of the run)
    printloop-ft evaluate --config configs/train_mi300x.yaml --base          # zero-shot baseline, same prompt
    printloop-ft serve-eval --base-url http://host:8080/v1 --model <name>    # GGUF on llama.cpp, or vLLM

Same prompt, same images (deterministic stratified subset of `test_limit` images) and greedy decoding
everywhere, so the numbers are comparable. Predictions are written to `results/<run_id>/predictions_<label>.jsonl`
(resumable) and the metrics to `results/<run_id>/eval_<label>.json`.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import statistics
import time
from pathlib import Path

import yaml

from fdmft.config import CHECKPOINTS, PROCESSED, RESULTS
from fdmft.metrics import by_source, evaluate
from fdmft.prompt import PROMPT_VERSION, USER_TEXT, messages, output_schema, parse, system_prompt
from fdmft.taxonomy import load as load_taxonomy
from fdmft.train import load_image, log, read_jsonl, stratified_subset


def _done(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {json.loads(line)["id"]: json.loads(line) for line in path.open() if line.strip()}


def _summary(rows: list[dict], results: dict[str, dict], tax, extra: dict) -> dict:
    res = [results[r["id"]] for r in rows if r["id"] in results]
    metrics = evaluate(res, tax.order)
    metrics["by_source"] = by_source(res, tax.order)
    return extra | {"prompt_version": PROMPT_VERSION, "test_images": len(res), "metrics": metrics}


def evaluate_model(model, processor, cfg: dict, run_id: str, label: str, dtype=None) -> dict:
    """Batched greedy generation (left padding) on the test subset."""
    import torch

    tax = load_taxonomy()
    rows = stratified_subset(read_jsonl(PROCESSED / cfg["build_id"] / "test.jsonl"), cfg.get("test_limit"))
    out_dir = RESULTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_file = out_dir / f"predictions_{label}.jsonl"
    done = _done(pred_file)
    todo = [r for r in rows if r["id"] not in done]
    bs = cfg.get("eval_batch_size", 8)
    if getattr(model, "is_gradient_checkpointing", False):
        model.gradient_checkpointing_disable()
    model.eval()
    model.config.use_cache = True
    processor.tokenizer.padding_side = "left"
    t0, n = time.perf_counter(), 0
    with pred_file.open("a") as fh:
        for i in range(0, len(todo), bs):
            chunk = todo[i:i + bs]
            images = [load_image(r["image"]) for r in chunk]
            texts = [processor.apply_chat_template(messages(img, tax), tokenize=False, add_generation_prompt=True)
                     for img in images]
            batch = processor(text=texts, images=[[img] for img in images], padding=True, return_tensors="pt")
            batch = batch.to(model.device)
            if dtype is not None:
                batch["pixel_values"] = batch["pixel_values"].to(dtype)
            with torch.inference_mode():
                out = model.generate(**batch, max_new_tokens=cfg.get("max_new_tokens", 64), do_sample=False)
            new = out[:, batch["input_ids"].shape[1]:]
            for r, seq in zip(chunk, new, strict=True):
                answer = processor.decode(seq, skip_special_tokens=True)
                valid, pred = parse(answer, tax)
                rec = {"id": r["id"], "source": r["source"], "gold": r["defects"], "pred": pred, "valid": valid,
                       "raw": answer[:300]}
                fh.write(json.dumps(rec) + "\n")
                done[r["id"]] = rec
            fh.flush()
            n += len(chunk)
            log(f"eval {label}: {len(done)}/{len(rows)} ({n / (time.perf_counter() - t0):.2f} img/s)")
    elapsed = time.perf_counter() - t0
    summary = _summary(rows, done, tax, {"run_id": run_id, "label": label, "model": cfg["model"],
                                         "images_per_s": round(n / elapsed, 3) if n else None,
                                         "eval_batch_size": bs})
    (out_dir / f"eval_{label}.json").write_text(json.dumps(summary, indent=1))
    m = summary["metrics"]
    log(f"{label}: primary accuracy {m['primary_accuracy']}, macro-F1 {m['macro_f1']}, "
        f"FP on none {m['binary']['false_positive_rate_on_none']}")
    return summary


def main_checkpoint(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="printloop-ft evaluate")
    ap.add_argument("--config", required=True)
    ap.add_argument("--base", action="store_true", help="zero-shot base model instead of the run adapter")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)
    from peft import PeftModel

    from fdmft.train import load_model

    cfg = yaml.safe_load(Path(args.config).read_text())
    run_id = args.run_id or cfg["run_id"]
    model, processor, dtype = load_model(cfg)
    if not args.base:
        model = PeftModel.from_pretrained(model, str(CHECKPOINTS / run_id / "adapter"))
    evaluate_model(model, processor, cfg, run_id, label="base" if args.base else "finetuned", dtype=dtype)
    return 0


def main_server(argv: list[str] | None = None) -> int:
    """Evaluation through an OpenAI-compatible server (llama-server with the GGUF, or vLLM)."""
    import requests

    ap = argparse.ArgumentParser(prog="printloop-ft serve-eval")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--build-id", default="v1")
    ap.add_argument("--run-id", default="serving")
    ap.add_argument("--label", required=True)
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args(argv)

    tax = load_taxonomy()
    rows = stratified_subset(read_jsonl(PROCESSED / args.build_id / "test.jsonl"), args.limit)
    out_dir = RESULTS / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_file = out_dir / f"predictions_{args.label}.jsonl"
    done = _done(pred_file)
    sess = requests.Session()
    if args.api_key:
        sess.headers["Authorization"] = f"Bearer {args.api_key}"
    system = system_prompt(tax)
    latencies = []
    with pred_file.open("a") as fh:
        for r in rows:
            if r["id"] in done:
                continue
            buf = io.BytesIO()
            load_image(r["image"]).save(buf, "JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            body = {
                "model": args.model, "temperature": 0.0, "max_tokens": 64,
                # llama.cpp's Jinja template turns Gemma 4 thinking on by default; the model was trained without
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "mode1", "schema": output_schema(tax), "strict": True}},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": [
                                 {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                 {"type": "text", "text": USER_TEXT}]}],
            }
            for attempt in range(30):          # the server may still be loading the model
                try:
                    t0 = time.perf_counter()
                    resp = sess.post(f"{args.base_url}/chat/completions", json=body, timeout=600)
                    if resp.status_code in (502, 503):
                        raise requests.ConnectionError(resp.text[:200])
                    resp.raise_for_status()
                    break
                except requests.RequestException as exc:
                    log(f"waiting for the server ({exc}); attempt {attempt + 1}")
                    time.sleep(10)
            else:
                raise SystemExit("the server does not answer")
            latency = (time.perf_counter() - t0) * 1000
            text = resp.json()["choices"][0]["message"].get("content") or ""
            valid, pred = parse(text, tax)
            rec = {"id": r["id"], "source": r["source"], "gold": r["defects"], "pred": pred, "valid": valid,
                   "latency_ms": round(latency), "raw": text[:200]}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[r["id"]] = rec
            latencies.append(latency)
            if len(latencies) % 100 == 0:
                log(f"{len(done)}/{len(rows)}")
    lat = sorted(x["latency_ms"] for x in done.values() if "latency_ms" in x)[1:]   # the first includes loading
    extra = {"label": args.label, "model": args.model, "base_url": args.base_url}
    if lat:
        extra["latency_ms"] = {"p50": statistics.median(lat), "p95": lat[int(0.95 * (len(lat) - 1))]}
    summary = _summary(rows, done, tax, extra)
    (out_dir / f"eval_{args.label}.json").write_text(json.dumps(summary, indent=1))
    m = summary["metrics"]
    log(f"{args.label}: primary accuracy {m['primary_accuracy']}, macro-F1 {m['macro_f1']}, latency {extra.get('latency_ms')}")
    return 0
