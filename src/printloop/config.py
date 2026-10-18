"""Central configuration, read from .env (see .env.example)."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

PACKAGE_DIR = Path(__file__).resolve().parent
KB_PATH = PACKAGE_DIR / "kb.yaml"
EXAMPLES_DIR = ROOT / "examples"

# Executables searched for when not set in .env. OrcaSlicer and BambuStudio share the same CLI, but each one
# rewrites the project in its own format: a project must be processed with the slicer that created it.
SLICER_CANDIDATES = {
    "orca": ("orca-slicer", "OrcaSlicer", "~/.local/bin/OrcaSlicer.AppImage", "~/Applications/OrcaSlicer.AppImage",
             "/opt/OrcaSlicer/bin/orca-slicer"),
    "bambu": ("bambu-studio", "/opt/BambuStudio/bin/bambu-studio"),
}
SLICER_ENV = {"orca": "ORCA_SLICER_BIN", "bambu": "BAMBU_STUDIO_BIN"}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class LLMConfig:
    base_url: str | None = _env("LLM_BASE_URL")
    api_key: str | None = _env("LLM_API_KEY")
    model: str = _env("LLM_MODEL", "google/gemma-4-26B-A4B-it")
    timeout_s: float = float(_env("LLM_TIMEOUT_S", "120"))
    # Headroom for models that reason before answering (reasoning_content): with 1200 tokens
    # Gemma 4 26B on llama.cpp sometimes truncates the JSON.
    max_tokens: int = int(_env("LLM_MAX_TOKENS", "4096"))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url) and "<" not in (self.base_url or "")


@dataclass(frozen=True)
class VisionLLMConfig:
    """Defect detector: Gemma 4 E4B fine-tuned (docs/printloop/07_VISION_MODEL.md), used by Mode 1 and Mode 2."""
    base_url: str | None = _env("VISION_LLM_BASE_URL")
    api_key: str | None = _env("VISION_LLM_API_KEY")
    model: str = _env("VISION_LLM_MODEL", "printloop-vision-e4b")
    # Short: a late answer is useless for a live frame. The first call after a model swap can take longer.
    timeout_s: float = float(_env("VISION_LLM_TIMEOUT_S", "30"))
    max_tokens: int = 64
    max_image_px: int = 1280    # long side of the training images (finetune prepare step)

    @property
    def enabled(self) -> bool:
        return bool(self.base_url) and "<" not in (self.base_url or "")


def _flag(name: str, default: bool) -> bool:
    value = _env(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Mode1Config:
    """Live monitoring (docs/printloop/08_MODE1_LIVE.md)."""
    source: str = _env("MODE1_SOURCE", "replay")
    replay_dir: str | None = _env("MODE1_REPLAY_DIR")
    snapshot_url: str | None = _env("MODE1_SNAPSHOT_URL")
    interval_s: float = float(_env("MODE1_INTERVAL_S", "10"))
    pause_k: int = int(_env("MODE1_PAUSE_K", "3"))
    pause_n: int = int(_env("MODE1_PAUSE_N", "4"))
    alert_k: int = int(_env("MODE1_ALERT_K", "4"))
    alert_n: int = int(_env("MODE1_ALERT_N", "6"))
    clear_n: int = int(_env("MODE1_CLEAR_N", "6"))
    record_all: bool = _flag("MODE1_RECORD_ALL", False)
    printer_ip: str | None = _env("PRINTER_IP")
    printer_serial: str | None = _env("PRINTER_SERIAL")
    printer_access_code: str | None = _env("PRINTER_ACCESS_CODE")


@dataclass(frozen=True)
class LoopConfig:
    runs_dir: Path = Path(_env("PRINTLOOP_RUNS_DIR", str(ROOT / "runs")))
    max_iterations: int = int(_env("PRINTLOOP_MAX_ITERATIONS", "3"))
    min_confidence: float = float(_env("PRINTLOOP_MIN_CONFIDENCE", "0.6"))
    max_image_px: int = int(_env("PRINTLOOP_MAX_IMAGE_PX", "1536"))
    max_photos: int = 4
    # Severity (0-3 rubric) at or below which the part is acceptable.
    accept_severity: int = 1
    max_changes: int = 2
    # Automatic proposal attempts when the validator or the pre-flight reject.
    propose_attempts: int = 3
    # Mode 2: the E4B detector labels each uploaded photo and the 26B gets the labels as a hint (09_MODE2_TWO_MODELS.md).
    detector: bool = _flag("MODE2_DETECTOR", True)


def _find(candidate: str) -> str | None:
    if "/" in candidate:
        path = Path(candidate).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate)


def slicer_bins() -> dict[str, str]:
    """Installed slicers by kind ("orca", "bambu"): from ORCA_SLICER_BIN / BAMBU_STUDIO_BIN or known paths."""
    found = {}
    for kind, candidates in SLICER_CANDIDATES.items():
        explicit = _env(SLICER_ENV[kind])
        path = _find(explicit) if explicit else next((p for c in candidates if (p := _find(c))), None)
        if path:
            found[kind] = path
    return found


def slicer_bin(kind: str | None = None) -> str | None:
    """SLICER_BIN forces a single slicer; otherwise the one of the requested kind, or the first available."""
    explicit = _env("SLICER_BIN")
    if explicit:
        return explicit
    bins = slicer_bins()
    if kind:
        return bins.get(kind)
    return bins.get("orca") or bins.get("bambu")


LLM = LLMConfig()
VISION_LLM = VisionLLMConfig()
MODE1 = Mode1Config()
LOOP = LoopConfig()
