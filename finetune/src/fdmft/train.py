"""LoRA fine-tuning of Gemma 4 E4B (vision + language) with transformers + PEFT, bf16.

    printloop-ft train --config configs/train_mi300x.yaml

Built for one AMD Instinct MI300X (ROCm PyTorch: the GPU shows up as `cuda`), runs unchanged on any bf16 GPU
with enough memory. No 4-bit quantization: with 192 GB the base stays in bf16, so the adapter merges back
exactly into the weights it was trained on.

- resumes from the last checkpoint in `checkpoints/<run_id>` (restart after an interruption);
- TensorBoard logs in `checkpoints/<run_id>/tb`;
- `results/<run_id>/train_metrics.json`: loss, wall time, s/step, samples/s, peak memory, device, ROCm/CUDA
  version: the numbers for a hardware comparison;
- at the end: adapter in `checkpoints/<run_id>/adapter`, then the generative evaluation on the test split
  (`fdmft.evaluate`).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import time
from datetime import datetime
from pathlib import Path

import yaml

from fdmft.config import CHECKPOINTS, DATA, PROCESSED, RESULTS
from fdmft.prompt import PROMPT_VERSION, messages
from fdmft.taxonomy import load as load_taxonomy

# LoRA targets: only plain nn.Linear modules. In the vision tower the projections are Gemma4ClippableLinear
# wrappers around an inner `.linear`, which is the one to adapt (PEFT rejects the wrapper itself).
LORA_TEXT = r"model\.language_model\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj|per_layer_input_gate|per_layer_projection)"
LORA_VISION = (r"model\.vision_tower\.encoder\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(gate|up|down)_proj)\.linear"
               r"|model\.vision_tower\.patch_embedder\.input_proj|model\.embed_vision\.embedding_projection")


def lora_targets(vision: bool) -> str:
    return rf"^(?:{LORA_TEXT}|{LORA_VISION})$" if vision else rf"^(?:{LORA_TEXT})$"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def read_jsonl(path: Path) -> list[dict]:
    """Rows of a build; `image` is relative to FDMFT_DATA_DIR."""
    rows = []
    with path.open() as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                img = Path(row["image"])
                row["image"] = str(img if img.is_absolute() else DATA / img)
                rows.append(row)
    return rows


def stratified_subset(rows: list[dict], limit: int | None, seed: int = 0) -> list[dict]:
    """Round-robin over the primary classes, deterministic: the same `limit` always gives the same images."""
    if not limit or len(rows) <= limit:
        return rows
    rng = random.Random(seed)
    by_cls: dict[str, list[dict]] = {}
    for r in rows:
        by_cls.setdefault(r["primary"], []).append(r)
    for items in by_cls.values():
        rng.shuffle(items)
    out, i = [], 0
    while len(out) < limit:
        for items in by_cls.values():
            if i < len(items) and len(out) < limit:
                out.append(items[i])
        i += 1
    return out


def load_image(path: str):
    from PIL import Image

    with Image.open(path) as im:
        return im.convert("RGB")


class Collator:
    """Batch of conversations -> model inputs, with the loss only on the assistant answer.

    The Gemma 4 chat template opens the model turn with `<|turn>model\\n`: every token up to the end of that
    marker is masked (-100), and so is the padding. The answer and the closing `<turn|>` are learned.
    """

    def __init__(self, processor, tax, dtype):
        self.processor, self.tax, self.dtype = processor, tax, dtype
        self.marker = processor.tokenizer.encode("<|turn>model\n", add_special_tokens=False)

    def _answer_start(self, ids: list[int]) -> int:
        m = len(self.marker)
        for i in range(len(ids) - m, -1, -1):
            if ids[i:i + m] == self.marker:
                return i + m
        raise ValueError("model turn marker not found in the rendered conversation")

    def __call__(self, rows: list[dict]) -> dict:
        images = [load_image(r["image"]) for r in rows]
        texts = [self.processor.apply_chat_template(messages(img, self.tax, list(r["defects"])), tokenize=False)
                 for img, r in zip(images, rows, strict=True)]
        batch = self.processor(text=texts, images=[[img] for img in images], padding=True, return_tensors="pt")
        labels = batch["input_ids"].clone()
        for i, ids in enumerate(batch["input_ids"].tolist()):
            labels[i, : self._answer_start(ids)] = -100
        labels[batch["attention_mask"] == 0] = -100
        batch["labels"] = labels
        batch["pixel_values"] = batch["pixel_values"].to(self.dtype)
        return batch


class RowDataset:
    """Plain list of build rows; images are opened by the collator (13k images do not fit in RAM)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        return self.rows[i]


def last_checkpoint(output_dir: Path) -> str | None:
    ckpts = sorted(output_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
    return str(ckpts[-1]) if ckpts else None


def device_info() -> dict:
    import torch

    info = {"torch": torch.__version__, "hip": getattr(torch.version, "hip", None), "cuda": torch.version.cuda,
            "host": platform.node(), "python": platform.python_version()}
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        info |= {"device": props.name, "device_memory_gb": round(props.total_memory / 2**30, 1),
                 "device_count": torch.cuda.device_count(),
                 "arch": getattr(props, "gcnArchName", None) or f"sm_{props.major}{props.minor}"}
    return info


def load_model(cfg: dict):
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    dtype = getattr(torch, cfg.get("dtype", "bfloat16"))
    processor = AutoProcessor.from_pretrained(cfg["model"])
    processor.image_processor.max_soft_tokens = cfg.get("max_soft_tokens", 280)
    model = AutoModelForImageTextToText.from_pretrained(
        cfg["model"], dtype=dtype, attn_implementation=cfg.get("attn_implementation", "sdpa"), device_map={"": 0})
    return model, processor, dtype


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="printloop-ft train")
    ap.add_argument("--config", required=True)
    ap.add_argument("--max-steps", type=int, default=None, help="override (smoke tests)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--no-eval", action="store_true", help="skip the final evaluation on the test split")
    args = ap.parse_args(argv)

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import Trainer, TrainerCallback, TrainingArguments

    cfg = yaml.safe_load(Path(args.config).read_text())
    run_id = args.run_id or cfg["run_id"]
    output_dir, results_dir = CHECKPOINTS / run_id, RESULTS / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    if not torch.cuda.is_available():
        raise SystemExit("no GPU visible to PyTorch (on ROCm check /dev/kfd and /dev/dri in the container)")
    dev = device_info()
    log(f"device: {dev}")

    tax = load_taxonomy()
    build_dir = PROCESSED / cfg["build_id"]
    train_rows = read_jsonl(build_dir / "train.jsonl")
    val_rows = stratified_subset(read_jsonl(build_dir / "val.jsonl"), cfg.get("val_limit", 200))
    log(f"run {run_id}: train {len(train_rows)}, val {len(val_rows)}, prompt {PROMPT_VERSION}")

    adapter_dir = output_dir / "adapter"
    model, processor, dtype = load_model(cfg)
    t = cfg["train"]
    if not (adapter_dir / "adapter_config.json").exists():
        lora = cfg["lora"]
        model.config.use_cache = False
        if t.get("gradient_checkpointing"):
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
            model.enable_input_require_grads()
        model = get_peft_model(model, LoraConfig(
            r=lora["r"], lora_alpha=lora["alpha"], lora_dropout=lora.get("dropout", 0.0), bias="none",
            target_modules=lora_targets(lora.get("vision", True))))
        trainable, total = model.get_nb_trainable_parameters()
        log(f"LoRA: {trainable:,} trainable parameters of {total:,} ({100 * trainable / total:.2f}%)")

        targs = TrainingArguments(
            output_dir=str(output_dir),
            per_device_train_batch_size=t["batch_size"],
            per_device_eval_batch_size=t["batch_size"],
            gradient_accumulation_steps=t["grad_accum"],
            num_train_epochs=t["epochs"],
            max_steps=args.max_steps or t.get("max_steps", -1),
            learning_rate=t["lr"],
            lr_scheduler_type="cosine",
            warmup_steps=t.get("warmup_steps", 50),
            weight_decay=t.get("weight_decay", 0.001),
            max_grad_norm=t.get("max_grad_norm", 0.3),
            optim=t.get("optim", "adamw_torch"),
            bf16=dtype == torch.bfloat16,
            logging_steps=t.get("logging_steps", 10),
            report_to=["tensorboard"],
            logging_dir=str(output_dir / "tb"),
            save_strategy="steps",
            save_steps=t.get("save_steps", 200),
            save_total_limit=3,
            eval_strategy="steps",
            eval_steps=t.get("eval_steps", 400),
            seed=cfg.get("seed", 3407),
            dataloader_num_workers=t.get("workers", 4),
            dataloader_persistent_workers=t.get("workers", 4) > 0,
            remove_unused_columns=False,
        )

        timing: dict = {"step_s": []}

        class Timing(TrainerCallback):
            def on_step_begin(self, *a, **k):
                timing["t0"] = time.perf_counter()

            def on_step_end(self, *a, **k):
                torch.cuda.synchronize()
                timing["step_s"].append(time.perf_counter() - timing["t0"])

        trainer = Trainer(model=model, args=targs, train_dataset=RowDataset(train_rows),
                          eval_dataset=RowDataset(val_rows), data_collator=Collator(processor, tax, dtype),
                          callbacks=[Timing()])
        resume = last_checkpoint(output_dir)
        log(f"training: {'resuming from ' + resume if resume else 'from scratch'}")
        torch.cuda.reset_peak_memory_stats()
        t_start = time.perf_counter()
        stats = trainer.train(resume_from_checkpoint=resume)
        wall = time.perf_counter() - t_start
        model.save_pretrained(str(adapter_dir))
        processor.save_pretrained(str(adapter_dir))
        steps = timing["step_s"][5:] or timing["step_s"]        # first steps include kernel warm-up
        per_step = sum(steps) / len(steps)
        eff_batch = t["batch_size"] * t["grad_accum"]
        metrics = stats.metrics | {
            "wall_s": round(wall, 1), "steps_timed": len(steps), "s_per_step": round(per_step, 3),
            "samples_per_s": round(eff_batch / per_step, 3), "effective_batch": eff_batch,
            "peak_memory_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
            "device": dev, "config": cfg, "run_id": run_id, "prompt_version": PROMPT_VERSION,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        (results_dir / "train_metrics.json").write_text(json.dumps(metrics, indent=1))
        log(f"training done: {per_step:.2f} s/step, {eff_batch / per_step:.2f} samples/s, "
            f"peak {metrics['peak_memory_gb']} GB, loss {stats.metrics.get('train_loss')}")
    else:
        from peft import PeftModel

        log(f"adapter already in {adapter_dir}: training skipped, loading it for the evaluation")
        model = PeftModel.from_pretrained(model, str(adapter_dir))

    if not args.no_eval:
        from fdmft.evaluate import evaluate_model

        evaluate_model(model, processor, cfg, run_id, label="finetuned", dtype=dtype)
    (output_dir / "DONE").write_text(datetime.now().isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
