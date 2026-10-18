"""Settings of a BambuStudio / OrcaSlicer 3MF project (Metadata/project_settings.config).

Values are strings or lists of strings (one entry per filament or per extruder variant), sometimes with
a '%' suffix. We read them as numbers and write them back in the same format. Declared MVP limit:
single-filament projects; in lists the patch writes every entry.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

PROJECT_SETTINGS = "Metadata/project_settings.config"
# Files of the 3MF that describe a previous slice: no longer valid after a patch.
_STALE_PREFIXES = ("Metadata/plate_", "Metadata/slice_info.config", "Metadata/top_", "Metadata/pick_")
_STALE_KEEP = ("Metadata/plate_1.json",)

BED_KEYS = {
    "Cool Plate": "cool_plate_temp",
    "Engineering Plate": "eng_plate_temp",
    "High Temp Plate": "hot_plate_temp",
    "Textured PEI Plate": "textured_plate_temp",
    "Supertack Plate": "supertack_plate_temp",
}

# Section of every real key PrintLoop can write, in the order of `different_settings_to_system`:
# [process, filament 1..n, printer]. Needed because OrcaSlicer, when it reopens a project, resets to the system
# preset value every key NOT listed there (PresetBundle::project_different_keys +
# Preset::load_external_config -> update_non_diff_values_to_base_config). See docs/printloop/01_RESEARCH_STACK.md.
_PLATE_KEYS = [f"{p}{suffix}" for p in ("cool_plate_temp", "eng_plate_temp", "hot_plate_temp", "textured_plate_temp",
                                        "supertack_plate_temp", "textured_cool_plate_temp")
               for suffix in ("", "_initial_layer")]
SECTION_OF: dict[str, str] = {
    "bridge_speed": "process", "bridge_flow": "process", "initial_layer_speed": "process",
    "brim_width": "process", "brim_type": "process",
    "filament_flow_ratio": "filament", "nozzle_temperature": "filament", "nozzle_temperature_initial_layer": "filament",
    "overhang_fan_speed": "filament", "filament_max_volumetric_speed": "filament",
    "filament_retraction_length": "filament", "filament_density": "filament",
    "retraction_length": "printer",
    **{k: "filament" for k in _PLATE_KEYS},
}

# Fallback density (g/cm³) when the preset lacks it: only used to estimate grams.
DEFAULT_DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PA": 1.12, "PC": 1.2, "PP": 0.9}


class ProjectError(ValueError):
    pass


def read_settings(path: str | Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read(PROJECT_SETTINGS))
    except KeyError as exc:
        raise ProjectError(f"{path}: {PROJECT_SETTINGS} is missing (a BambuStudio/OrcaSlicer 3MF project is required)") from exc
    except zipfile.BadZipFile as exc:
        raise ProjectError(f"{path}: not a valid 3MF file") from exc


def _first(raw: Any) -> Any:
    return raw[0] if isinstance(raw, list) and raw else raw


def to_number(raw: Any) -> float | None:
    """'0.98' -> 0.98, ['220'] -> 220.0, '50%' -> 50.0, 'nil' or text -> None."""
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
    """Writes `value` in the same format as the original value (list or scalar, with or without '%')."""
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
    """Keys the user changed against the system profiles (recorded by the slicer in the project)."""
    raw = settings.get("different_settings_to_system") or []
    raw = raw if isinstance(raw, list) else [raw]
    return {k.strip() for chunk in raw for k in str(chunk).split(";") if k.strip()}


def resolve_keys(settings: dict, key: str, meta: dict | None = None) -> list[str]:
    """Real keys to change for a KB key (aliases and filament overrides)."""
    meta = meta or {}
    if meta.get("alias") == "bed_temperature":
        base = bed_key(settings)
        return [base, f"{base}_initial_layer"]
    override = meta.get("filament_override")
    if override and get(settings, override) is not None:
        return [override]
    return [key]


def current_value(settings: dict, key: str, meta: dict | None = None) -> float | None:
    """Effective value of the KB key (for aliases: the first real key)."""
    return get(settings, resolve_keys(settings, key, meta)[0])


def apply_changes(settings: dict, changes: dict[str, float | str]) -> dict:
    """Returns a copy of the settings with `changes` (real keys) applied in the original format."""
    patched = dict(settings)
    for key, value in changes.items():
        if key not in settings:
            raise ProjectError(f"key '{key}' missing in the project")
        patched[key] = format_like(settings[key], value)
    return patched


def write_patched(src: str | Path, dst: str | Path, settings: dict) -> Path:
    """Copies the 3MF replacing the settings and dropping G-code and previews of the previous slice."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Sanitize known keys that OrcaSlicer rejects if negative (BambuStudio default -1)
    sanitized = dict(settings)
    for key in ("raft_first_layer_expansion", "tree_support_wall_count"):
        val = sanitized.get(key)
        if val in (-1, "-1", -1.0):
            sanitized[key] = "0"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            if name.startswith(_STALE_PREFIXES) and name not in _STALE_KEEP:
                continue
            data = json.dumps(sanitized, indent=4).encode() if name == PROJECT_SETTINGS else zin.read(name)
            zout.writestr(item, data)
    return dst


def section_of(key: str) -> str | None:
    if key in SECTION_OF:
        return SECTION_OF[key]
    return "filament" if key.startswith("filament_") else None


def num_filaments(settings: dict) -> int:
    for key in ("filament_colour", "filament_settings_id"):
        value = settings.get(key)
        if isinstance(value, list) and value:
            return len(value)
    return 1


def different_lists(settings: dict) -> list[str]:
    """`different_settings_to_system` as [process, filament 1..n, printer], padded with empty strings."""
    size = num_filaments(settings) + 2
    raw = settings.get("different_settings_to_system")
    values = [str(v) for v in raw] if isinstance(raw, list) else ([str(raw)] if raw else [])
    return (values + [""] * size)[:max(size, len(values))]


def _section_indices(settings: dict, section: str) -> list[int]:
    n = num_filaments(settings)
    return {"process": [0], "filament": list(range(1, n + 1)), "printer": [n + 1]}[section]


def mark_different(settings: dict, keys) -> tuple[dict, list[str]]:
    """Declares `keys` as modified against the system preset, so the slicer keeps them when reopening.

    Union with what is already listed; returns (updated settings, keys without a known section).
    """
    lists = different_lists(settings)
    unknown = []
    for key in keys:
        section = section_of(key)
        if section is None:
            unknown.append(key)
            continue
        for idx in _section_indices(settings, section):
            current = {k for k in lists[idx].split(";") if k}
            current.add(key)
            lists[idx] = ";".join(sorted(current))
    updated = dict(settings)
    updated["different_settings_to_system"] = lists
    return updated, unknown


def is_marked(settings: dict, key: str) -> bool:
    """True if the key is listed as modified in every entry of its section."""
    section = section_of(key)
    if section is None:
        return False
    lists = different_lists(settings)
    return all(key in lists[idx].split(";") for idx in _section_indices(settings, section))


def rewrite_settings(path: str | Path, settings: dict) -> Path:
    """Replaces only Metadata/project_settings.config in a 3MF, leaving G-code and metadata intact."""
    path = Path(path)
    tmp = path.with_suffix(".tmp.3mf")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = json.dumps(settings, indent=4).encode() if item.filename == PROJECT_SETTINGS else zin.read(item.filename)
            zout.writestr(item, data)
    tmp.replace(path)
    return path


def diff(before: dict, after: dict) -> dict[str, tuple[Any, Any]]:
    return {k: (before.get(k), after.get(k)) for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)}
