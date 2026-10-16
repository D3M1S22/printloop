"""Accesso alla knowledge base deterministica (kb.yaml)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from printloop import project
from printloop.config import KB_PATH


@dataclass(frozen=True)
class Candidate:
    key: str
    direction: str  # "up" | "down"
    label: str
    unit: str
    step: float
    check: dict
    meta: dict

    @property
    def sign(self) -> int:
        return 1 if self.direction == "up" else -1


@lru_cache(maxsize=1)
def load() -> dict:
    with open(KB_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def param(key: str) -> dict:
    try:
        return load()["params"][key]
    except KeyError as exc:
        raise KeyError(f"parametro '{key}' non presente nella KB") from exc


def candidates(defect: str) -> list[Candidate]:
    entry = load()["defects"].get(defect, {})
    out = []
    for c in entry.get("candidates", []):
        meta = param(c["key"])
        out.append(Candidate(key=c["key"], direction=c["direction"], label=meta["label"], unit=meta["unit"],
                             step=float(meta["step"]), check=meta["check"], meta=meta))
    return out


def escalation(defect: str) -> str | None:
    return load()["defects"].get(defect, {}).get("escalate")


def bounds(key: str, settings: dict) -> tuple[float, float]:
    """Range ammesso per la chiave, inclusi i limiti del materiale."""
    meta = param(key)
    raw = meta["bounds"]
    if raw == "filament_range":
        rng = project.filament_range(settings)
        lo, hi = rng if rng else (180.0, 300.0)
    else:
        lo, hi = float(raw[0]), float(raw[1])
    if meta.get("alias") == "bed_temperature":
        cap = load()["material_bed_max"].get(project.material(settings))
        if cap is not None:
            hi = min(hi, float(cap))
    return lo, hi
