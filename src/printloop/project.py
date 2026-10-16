"""Impostazioni di un progetto 3MF (Metadata/project_settings.config) di BambuStudio / OrcaSlicer.

I valori sono stringhe o liste di stringhe (una voce per filamento o per variante di estrusore), a volte
con il suffisso '%'. Li leggiamo come numeri e li riscriviamo nello stesso formato. Limite dichiarato
dell'MVP: progetti mono-filamento; nelle liste la patch scrive tutte le voci.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

PROJECT_SETTINGS = "Metadata/project_settings.config"
# File del 3MF che descrivono uno slicing precedente: dopo una patch non valgono più.
_STALE_PREFIXES = ("Metadata/plate_", "Metadata/slice_info.config", "Metadata/top_", "Metadata/pick_")
_STALE_KEEP = ("Metadata/plate_1.json",)

BED_KEYS = {
    "Cool Plate": "cool_plate_temp",
    "Engineering Plate": "eng_plate_temp",
    "High Temp Plate": "hot_plate_temp",
    "Textured PEI Plate": "textured_plate_temp",
    "Supertack Plate": "supertack_plate_temp",
}

# Densità di riserva (g/cm³) se il preset non la riporta: serve solo a stimare i grammi.
DEFAULT_DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PA": 1.12, "PC": 1.2, "PP": 0.9}


class ProjectError(ValueError):
    pass


def read_settings(path: str | Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read(PROJECT_SETTINGS))
    except KeyError as exc:
        raise ProjectError(f"{path}: manca {PROJECT_SETTINGS} (serve un progetto 3MF di BambuStudio/OrcaSlicer)") from exc
    except zipfile.BadZipFile as exc:
        raise ProjectError(f"{path}: non è un file 3MF valido") from exc


def _first(raw: Any) -> Any:
    return raw[0] if isinstance(raw, list) and raw else raw


def to_number(raw: Any) -> float | None:
    """'0.98' -> 0.98, ['220'] -> 220.0, '50%' -> 50.0, 'nil' o testo -> None."""
    value = _first(raw)
    if value is None:
        return None
    text = str(value).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def _fmt(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def format_like(original: Any, value: float | str) -> Any:
    """Scrive `value` con lo stesso formato del valore originale (lista o scalare, con o senza '%')."""
    sample = str(_first(original)) if original is not None else ""
    if isinstance(value, str):
        text = value
    else:
        text = _fmt(value) + ("%" if sample.endswith("%") else "")
    if isinstance(original, list):
        return [text] * max(1, len(original))
    return text


def get(settings: dict, key: str) -> float | None:
    return to_number(settings.get(key))


def get_text(settings: dict, key: str) -> str | None:
    value = _first(settings.get(key))
    return None if value is None else str(value)


def material(settings: dict) -> str:
    return (get_text(settings, "filament_type") or "PLA").upper()


def bed_key(settings: dict) -> str:
    return BED_KEYS.get(get_text(settings, "curr_bed_type") or "", "hot_plate_temp")


def filament_range(settings: dict) -> tuple[float, float] | None:
    low, high = get(settings, "nozzle_temperature_range_low"), get(settings, "nozzle_temperature_range_high")
    return (low, high) if low is not None and high is not None else None


def density(settings: dict) -> float:
    value = get(settings, "filament_density")
    return value if value else DEFAULT_DENSITY.get(material(settings), 1.24)


def modified_keys(settings: dict) -> set[str]:
    """Chiavi che l'utente ha cambiato rispetto ai profili di sistema (registrate dallo slicer nel progetto)."""
    raw = settings.get("different_settings_to_system") or []
    raw = raw if isinstance(raw, list) else [raw]
    return {k.strip() for chunk in raw for k in str(chunk).split(";") if k.strip()}


def resolve_keys(settings: dict, key: str, meta: dict | None = None) -> list[str]:
    """Chiavi reali da modificare per una chiave della KB (alias e override di filamento)."""
    meta = meta or {}
    if meta.get("alias") == "bed_temperature":
        base = bed_key(settings)
        return [base, f"{base}_initial_layer"]
    override = meta.get("filament_override")
    if override and get(settings, override) is not None:
        return [override]
    return [key]


def current_value(settings: dict, key: str, meta: dict | None = None) -> float | None:
    """Valore effettivo della chiave della KB (per gli alias: la prima chiave reale)."""
    return get(settings, resolve_keys(settings, key, meta)[0])


def apply_changes(settings: dict, changes: dict[str, float | str]) -> dict:
    """Restituisce una copia delle impostazioni con `changes` (chiavi reali) applicate nel formato originale."""
    patched = dict(settings)
    for key, value in changes.items():
        if key not in settings:
            raise ProjectError(f"chiave '{key}' assente nel progetto")
        patched[key] = format_like(settings[key], value)
    return patched


def write_patched(src: str | Path, dst: str | Path, settings: dict) -> Path:
    """Copia il 3MF sostituendo le impostazioni e togliendo G-code e anteprime dello slicing precedente."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            if name.startswith(_STALE_PREFIXES) and name not in _STALE_KEEP:
                continue
            data = json.dumps(settings, indent=4).encode() if name == PROJECT_SETTINGS else zin.read(name)
            zout.writestr(item, data)
    return dst


def diff(before: dict, after: dict) -> dict[str, tuple[Any, Any]]:
    return {k: (before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)}
