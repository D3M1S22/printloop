"""Paths and settings from the environment (optional `finetune/.env`)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # the finetune/ directory
CONFIGS = ROOT / "configs"


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

DATA = Path(os.environ.get("FDMFT_DATA_DIR", ROOT / "data")).resolve()
RAW = DATA / "raw"
INTERIM = DATA / "interim"
IMAGES = INTERIM / "images"
MANIFEST = INTERIM / "manifest.jsonl"
PROCESSED = DATA / "processed"
CHECKPOINTS = Path(os.environ.get("FDMFT_CHECKPOINTS_DIR", ROOT / "checkpoints")).resolve()
RESULTS = Path(os.environ.get("FDMFT_RESULTS_DIR", ROOT / "results")).resolve()

ROBOFLOW_API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")
