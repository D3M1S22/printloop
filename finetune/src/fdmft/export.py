"""Export: merged Hugging Face weights (for vLLM) and GGUF + mmproj (for llama.cpp).

    printloop-ft export --config configs/train_mi300x.yaml [--quants Q8_0,Q4_K_M]

1. merge of the LoRA adapter into the bf16 base (`merge_and_unload`): the base is the same bf16 model the adapter
   was trained on, so the merge is exact;
2. `convert_hf_to_gguf.py` of llama.cpp: text model F16 and Q8_0, `--mmproj` F16. The vision projector must be
   regenerated from the merged model: the LoRA also changes the vision encoder;
3. optional `llama-quantize` (Q4_K_M, ...) if the binary is available.

Output in `export/<run_id>/`: `merged/` (safetensors + processor), `gguf/*.gguf` and `gguf/manifest.json` with the
sha256 of every file. Always check the sha256 after copying a GGUF to the inference host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from fdmft.config import CHECKPOINTS, ROOT
from fdmft.train import log

EXPORT = Path(os.environ.get("FDMFT_EXPORT_DIR", ROOT / "export")).resolve()
LLAMA_CPP_REPO = os.environ.get("LLAMA_CPP_REPO", "https://github.com/ggml-org/llama.cpp.git")
LLAMA_CPP_REF = os.environ.get("LLAMA_CPP_REF", "efe3626b119ff81033e309c3ba07a770bef2c546")   # 12 Oct 2026, Gemma 4 vision


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def sh(cmd: list[str]) -> None:
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def llama_cpp_dir() -> Path:
    """llama.cpp checkout: $LLAMA_CPP_DIR, or a clone at LLAMA_CPP_REF in export/llama.cpp."""
    if os.environ.get("LLAMA_CPP_DIR"):
        return Path(os.environ["LLAMA_CPP_DIR"])
    d = EXPORT / "llama.cpp"
    if not (d / "convert_hf_to_gguf.py").exists():
        sh(["git", "clone", "--filter=blob:none", LLAMA_CPP_REPO, str(d)])
        sh(["git", "-C", str(d), "checkout", LLAMA_CPP_REF])
        sh([sys.executable, "-m", "pip", "install", "--no-deps", "-e", str(d / "gguf-py")])
    return d


def merge(cfg: dict, run_id: str, out: Path) -> Path:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor

    merged = out / "merged"
    if (merged / "config.json").exists():
        return merged
    adapter = CHECKPOINTS / run_id / "adapter"
    log(f"merge: {cfg['model']} + {adapter}")
    model = AutoModelForImageTextToText.from_pretrained(cfg["model"], dtype=torch.bfloat16, device_map="cpu")
    model = PeftModel.from_pretrained(model, str(adapter)).merge_and_unload()
    tmp = out / "merged.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    model.save_pretrained(str(tmp), safe_serialization=True, max_shard_size="4GB")
    processor = AutoProcessor.from_pretrained(cfg["model"])
    processor.image_processor.max_soft_tokens = cfg.get("max_soft_tokens", 280)
    processor.save_pretrained(str(tmp))
    tmp.rename(merged)
    return merged


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="printloop-ft export")
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--name", default="gemma-4-E4B-3dprint", help="file name prefix of the GGUFs")
    ap.add_argument("--quants", default="Q8_0", help="comma-separated: Q8_0 (direct), Q4_K_M, ... (llama-quantize)")
    ap.add_argument("--merge-only", action="store_true", help="only the merged HF weights (for vLLM)")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())
    run_id = args.run_id or cfg["run_id"]
    out = EXPORT / run_id
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    merged = merge(cfg, run_id, out)
    if args.merge_only:
        log(f"merged weights in {merged}")
        return 0

    llama = llama_cpp_dir()
    gguf = out / "gguf"
    gguf.mkdir(exist_ok=True)
    quants = [q for q in args.quants.split(",") if q]
    convert = [sys.executable, str(llama / "convert_hf_to_gguf.py"), str(merged), "--model-name", args.name]
    files = {"F16": gguf / f"{args.name}-F16.gguf", "mmproj-F16": gguf / f"mmproj-{args.name}-F16.gguf"}
    sh([*convert, "--outtype", "f16", "--outfile", str(files["F16"])])
    sh([*convert, "--mmproj", "--outtype", "f16", "--outfile", str(files["mmproj-F16"])])
    for q in quants:
        files[q] = gguf / f"{args.name}-{q}.gguf"
        if q == "Q8_0":
            sh([*convert, "--outtype", "q8_0", "--outfile", str(files[q])])
            continue
        quantize = os.environ.get("LLAMA_QUANTIZE") or shutil.which("llama-quantize") \
            or str(llama / "build/bin/llama-quantize")
        if not Path(quantize).exists():
            log(f"{q}: llama-quantize not found (build llama.cpp or set LLAMA_QUANTIZE): skipped")
            files.pop(q)
            continue
        sh([quantize, str(files["F16"]), str(files[q]), q])
    manifest = {"run_id": run_id, "base_model": cfg["model"], "llama_cpp": f"{LLAMA_CPP_REPO}@{LLAMA_CPP_REF}",
                "files": {k: {"file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for k, p in files.items()},
                "seconds": round(time.monotonic() - t0)}
    (gguf / "manifest.json").write_text(json.dumps(manifest, indent=1))
    log(f"export done: {gguf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
