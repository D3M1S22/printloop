"""Test coupon and test set with induced defects (docs/printloop/02_DATA_STRATEGY.md §3).

The coupon is our own model (boxes): a 60×20×2 mm plate, two 8×8 mm pillars 13 mm tall and a 44 mm
bridge on top. In ~12 minutes it shows bridges, stringing between the pillars (travel), walls and the
first layer. The project is built from the BambuStudio system presets for P1S 0.4 + Bambu PLA Basic.

Each test case changes only the parameters declared in its manifest against the baseline; the manifest
also states the expected patch: it is the ground truth of the cause.
"""
from __future__ import annotations

import json
import struct
import subprocess
import tempfile
from pathlib import Path

from printloop import project
from printloop.config import EXAMPLES_DIR, ROOT, slicer_bin
from printloop.slicer import SlicerError, slice_project

COUPON_3MF = EXAMPLES_DIR / "coupon" / "coupon_p1s_pla.3mf"
MACHINE = "Bambu Lab P1S 0.4 nozzle"
PROCESS = "0.20mm Standard @BBL X1C"
FILAMENT = "Bambu PLA Basic @BBL P1S 0.4 nozzle"

# id, expected defect, induced parameters (real keys), expected patch (KB key, direction), note
CASES: list[dict] = [
    {"id": "C0_baseline", "defect": "none", "induced": {}, "expected": {}, "note": "negative control"},
    {"id": "C1_bridge_speed", "defect": "bridge_sagging", "induced": {"bridge_speed": 100},
     "expected": {"bridge_speed": "down"}, "note": "bridges at double speed"},
    {"id": "C2_bridge_cooling", "defect": "bridge_sagging",
     "induced": {"overhang_fan_speed": 20, "fan_max_speed": 30},
     "expected": {"overhang_fan_speed": "up"},
     "note": "low fan on bridges and short layers; with fan_max at 100% the bridge fan would not change"},
    {"id": "C3_over_extrusion", "defect": "over_extrusion", "induced": {"filament_flow_ratio": 1.13},
     "expected": {"filament_flow_ratio": "down"}, "note": "flow +15%"},
    {"id": "C4_under_extrusion", "defect": "under_extrusion", "induced": {"filament_flow_ratio": 0.8},
     "expected": {"filament_flow_ratio": "up"}, "note": "flow -18%"},
    {"id": "C5_stringing_temp", "defect": "stringing", "induced": {"nozzle_temperature": 240},
     "expected": {"nozzle_temperature": "down"}, "note": "nozzle +20 °C (top of the PLA range)"},
    {"id": "C6_stringing_retraction", "defect": "stringing", "induced": {"retraction_length": 0.1},
     "expected": {"retraction_length": "up"}, "note": "almost no retraction"},
    {"id": "C7_first_layer_speed", "defect": "first_layer", "induced": {"initial_layer_speed": 100},
     "expected": {"initial_layer_speed": "down"}, "note": "first layer at double speed"},
]


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> list[tuple]:
    v = {(i, j, k): (x1 if i else x0, y1 if j else y0, z1 if k else z0) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    quads = [((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
             ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
             ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))]
    tris = []
    for a, b, c, d in quads:
        tris += [(v[a], v[b], v[c]), (v[a], v[c], v[d])]
    return tris


def write_coupon_stl(path: Path) -> Path:
    tris = (_box(0, 0, 0, 60, 20, 2) + _box(0, 6, 2, 8, 14, 15) + _box(52, 6, 2, 60, 14, 15)
            + _box(0, 6, 15, 60, 14, 17))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"PrintLoop coupon".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for tri in tris:
            fh.write(struct.pack("<3f", 0, 0, 0))
            for p in tri:
                fh.write(struct.pack("<3f", *p))
            fh.write(b"\0\0")
    return path


def _builder_bin() -> str | None:
    """The coupon is built with BambuStudio (system presets in /opt/BambuStudio), when available."""
    return slicer_bin("bambu") or slicer_bin()


def profiles_dir() -> Path:
    """BBL system preset folder of the installed slicer."""
    binary = _builder_bin()
    candidates = [
        Path("/var/lib/flatpak/app/com.orcaslicer.OrcaSlicer/current/active/files/share/OrcaSlicer/profiles/BBL"),
        Path("/opt/BambuStudio/resources/profiles/BBL"),
        Path("/usr/share/BambuStudio/profiles/BBL"),
        Path("/opt/OrcaSlicer/resources/profiles/BBL"),
        Path("/usr/share/OrcaSlicer/profiles/BBL"),
    ]
    if binary:
        real = Path(binary).resolve()
        candidates.insert(0, real.parent.parent / "resources" / "profiles" / "BBL")
    for path in candidates:
        if (path / "machine" / f"{MACHINE}.json").exists():
            return path
    raise SlicerError("BBL system presets not found: set the path in testset.profiles_dir()")


def build_coupon(dst: Path = COUPON_3MF) -> Path:
    """Builds the coupon 3MF project from the system presets (without G-code inside)."""
    binary = _builder_bin()
    if not binary:
        raise SlicerError("slicer not found")
    prof = profiles_dir()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stl = write_coupon_stl(tmp / "printloop_coupon.stl")
        cmd = [binary, str(stl),
               "--load-settings", f"{prof}/machine/{MACHINE}.json;{prof}/process/{PROCESS}.json",
               "--load-filaments", f"{prof}/filament/{FILAMENT}.json",
               "--arrange", "1", "--orient", "0", "--slice", "1", "--export-3mf", "coupon.3mf",
               "--outputdir", str(tmp)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0 or not (tmp / "coupon.3mf").exists():
            raise SlicerError(f"coupon build failed (exit {proc.returncode})")
        settings = project.read_settings(tmp / "coupon.3mf")
        # Presets loaded from the CLI do not inherit the density: set it to estimate grams.
        settings = project.apply_changes(settings, {"filament_density": 1.26})
        project.write_patched(tmp / "coupon.3mf", dst, settings)
    return dst


def build_testset(outdir: Path, base: Path = COUPON_3MF, slice_cases: bool = True,
                  bed_type: str | None = None) -> list[dict]:
    """Writes one project per case (plus the sliced 3MF to print) and the manifest with the ground truth.

    `bed_type` (e.g. "Textured PEI Plate") sets the plate that will actually be used.
    """
    if not base.exists():
        build_coupon(base)
    settings = project.read_settings(base)
    if bed_type:
        if bed_type not in project.BED_KEYS:
            raise ValueError(f"unknown plate: {bed_type} (allowed: {', '.join(project.BED_KEYS)})")
        settings = project.apply_changes(settings, {"curr_bed_type": bed_type})
    manifest = []
    for case in CASES:
        folder = outdir / case["id"]
        patched = project.apply_changes(settings, case["induced"])
        proj = project.write_patched(base, folder / "project.3mf", patched)
        entry = {
            "case_id": case["id"], "object": "printloop_coupon", "induced_defect": case["defect"],
            "induced_params": {k: [project.get(settings, k), v] for k, v in case["induced"].items()},
            "expected_patch": case["expected"], "note": case["note"],
            "printer": project.get_text(settings, "printer_settings_id"),
            "filament": project.get_text(settings, "filament_settings_id"),
            "bed_type": project.get_text(settings, "curr_bed_type"),
        }
        if slice_cases:
            result = slice_project(proj, folder / "slice")
            entry["print_file"] = str((folder / "slice" / result.sliced_3mf.name).relative_to(outdir))
            entry["print_time_min"] = round((result.print_time_s or 0) / 60, 1)
        (folder / "manifest.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest.append(entry)
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


DEFAULT_TESTSET_DIR = ROOT / "data" / "testset"
