"""Configurazione centrale, letta da .env (vedi .env.example)."""
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

# Eseguibili cercati nel PATH se SLICER_BIN non è impostato: OrcaSlicer e BambuStudio hanno la stessa CLI.
SLICER_CANDIDATES = ("orca-slicer", "OrcaSlicer", "bambu-studio")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class LLMConfig:
    base_url: str | None = _env("LLM_BASE_URL")
    api_key: str | None = _env("LLM_API_KEY")
    model: str = _env("LLM_MODEL", "google/gemma-4-26B-A4B-it")
    timeout_s: float = float(_env("LLM_TIMEOUT_S", "120"))
    # Margine anche per i modelli che ragionano prima di rispondere (reasoning_content): con 1200 token
    # Gemma 4 26B su llama.cpp a volte tronca il JSON.
    max_tokens: int = int(_env("LLM_MAX_TOKENS", "4096"))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url) and "<" not in (self.base_url or "")


@dataclass(frozen=True)
class LoopConfig:
    runs_dir: Path = Path(_env("PRINTLOOP_RUNS_DIR", str(ROOT / "runs")))
    max_iterations: int = int(_env("PRINTLOOP_MAX_ITERATIONS", "3"))
    min_confidence: float = float(_env("PRINTLOOP_MIN_CONFIDENCE", "0.6"))
    max_image_px: int = int(_env("PRINTLOOP_MAX_IMAGE_PX", "1536"))
    max_photos: int = 4
    # Severità (rubrica 0-3) sotto o uguale alla quale il pezzo è accettabile.
    accept_severity: int = 1
    max_changes: int = 2
    # Tentativi automatici di proposta quando validatore o pre-flight rifiutano.
    propose_attempts: int = 3


def slicer_bin() -> str | None:
    explicit = _env("SLICER_BIN")
    if explicit:
        return explicit
    for name in SLICER_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


LLM = LLMConfig()
LOOP = LoopConfig()
