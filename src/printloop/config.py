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

# Eseguibili cercati se non indicati in .env. OrcaSlicer e BambuStudio hanno la stessa CLI, ma ognuno
# riscrive il progetto nel proprio formato: un progetto va lavorato con lo slicer che l'ha creato.
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


def _find(candidate: str) -> str | None:
    if "/" in candidate:
        path = Path(candidate).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate)


def slicer_bins() -> dict[str, str]:
    """Slicer installati per tipo ("orca", "bambu"): da ORCA_SLICER_BIN / BAMBU_STUDIO_BIN o dai percorsi noti."""
    found = {}
    for kind, candidates in SLICER_CANDIDATES.items():
        explicit = _env(SLICER_ENV[kind])
        path = _find(explicit) if explicit else next((p for c in candidates if (p := _find(c))), None)
        if path:
            found[kind] = path
    return found


def slicer_bin(kind: str | None = None) -> str | None:
    """SLICER_BIN forza un unico slicer; altrimenti quello del tipo richiesto, o il primo disponibile."""
    explicit = _env("SLICER_BIN")
    if explicit:
        return explicit
    bins = slicer_bins()
    if kind:
        return bins.get(kind)
    return bins.get("orca") or bins.get("bambu")


LLM = LLMConfig()
LOOP = LoopConfig()
