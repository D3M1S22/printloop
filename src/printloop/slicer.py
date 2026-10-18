"""Wrapper of the BambuStudio / OrcaSlicer CLI (same interface: --slice, --export-3mf, --outputdir).

Verified headless (no display) on BambuStudio 2.8.2 and OrcaSlicer 2.4.2 AppImage: with `--outputdir`
the slicer writes `plate_<n>.gcode` and `result.json` next to the exported 3MF.

Each slicer rewrites the project in its own format: an OrcaSlicer project re-exported by BambuStudio
loses the settings that exist only in Orca (e.g. chamber_temperature) and does not reopen faithfully.
So a project is processed with the slicer that created it (`OrcaSlicer` tag in the 3MF metadata).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from printloop.config import slicer_bin, slicer_bins


class SlicerError(RuntimeError):
    pass


def _parse_gcode_time(gcode_path: Path) -> float | None:
    """Reads the estimated time (seconds) from the G-code header when result.json does not report it."""
    try:
        with open(gcode_path, encoding="utf-8", errors="replace") as fh:
            for _ in range(120):
                line = fh.readline()
                if not line:
                    break
                m = re.search(r"total estimated time\s*:\s*([^;\n\r]+)", line)
                if m:
                    raw = m.group(1).strip()
                    dur = re.search(r"(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m\s*)?(?:(\d+)\s*s)?", raw)
                    if dur:
                        d, h, m_val, s = dur.groups()
                        tot = int(d or 0) * 86400 + int(h or 0) * 3600 + int(m_val or 0) * 60 + int(s or 0)
                        if tot > 0:
                            return float(tot)
    except OSError:
        pass
    return None


@dataclass
class SliceResult:
    project: Path       # input 3MF
    sliced_3mf: Path    # 3MF with G-code, ready to print
    gcode: Path
    result: dict        # the slicer's result.json
    elapsed_s: float
    slicer: str = ""    # version of the slicer used
    notes: list[str] = field(default_factory=list)

    @property
    def print_time_s(self) -> float | None:
        plates = self.result.get("sliced_plates") or [{}]
        pred = plates[0].get("total_predication")
        if pred is not None and pred > 0:
            return float(pred)
        if self.gcode and Path(self.gcode).exists():
            return _parse_gcode_time(Path(self.gcode))
        return None

    def summary(self) -> dict:
        return {"sliced_3mf": self.sliced_3mf.name, "gcode": self.gcode.name,
                "print_time_s": self.print_time_s, "slice_elapsed_s": round(self.elapsed_s, 2),
                "slicer": self.slicer, "notes": self.notes}


def available() -> bool:
    return slicer_bin() is not None


def project_origin(project: str | Path) -> str:
    """"orca" if the 3MF carries the OrcaSlicer tag in its metadata, otherwise "bambu"."""
    try:
        with zipfile.ZipFile(project) as zf:
            model = zf.read("3D/3dmodel.model").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile, OSError):
        return "bambu"
    return "orca" if 'name="OrcaSlicer"' in model else "bambu"


def choose(project: str | Path) -> tuple[str, list[str]]:
    """Slicer for the project: SLICER_BIN if set, then the one that created it, then the other one with a warning."""
    forced = slicer_bin() if _forced() else None
    if forced:
        return forced, []
    origin = project_origin(project)
    bins = slicer_bins()
    if origin in bins:
        return bins[origin], []
    other = next(iter(bins.values()), None)
    if other is None:
        raise SlicerError("slicer not found: install OrcaSlicer or BambuStudio, or set SLICER_BIN")
    name = {"orca": "OrcaSlicer", "bambu": "BambuStudio"}[origin]
    return other, [f"Project created with {name}, which is not installed: slicing uses {Path(other).name} and "
                   "some slicer-specific settings may not be honoured."]


def _forced() -> bool:
    return bool(os.getenv("SLICER_BIN"))


@lru_cache(maxsize=4)
def version(binary: str | None = None) -> str | None:
    binary = binary or slicer_bin()
    if not binary:
        return None
    try:
        # temporary cwd: even with --help the slicer writes result.json into the current folder
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=60, cwd=tmp)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in (out.stdout + out.stderr).splitlines():
        if not line.startswith("[") and ("BambuStudio-" in line or "OrcaSlicer" in line):
            return line.strip().rstrip(":")
    return Path(binary).name


def slice_project(project: str | Path, outdir: str | Path, plate: int = 1, timeout_s: int = 600) -> SliceResult:
    """Slices one plate of the project and returns the G-code and the printable 3MF."""
    project, outdir = Path(project), Path(outdir)
    binary, notes = choose(project)
    outdir.mkdir(parents=True, exist_ok=True)
    sliced = outdir / "sliced.3mf"
    cmd = [binary, str(project.resolve()), "--slice", str(plate), "--export-3mf", sliced.name,
           "--outputdir", str(outdir.resolve())]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise SlicerError(f"slicing took longer than {timeout_s} s") from exc
    elapsed = time.perf_counter() - t0
    (outdir / "slicer.log").write_text(proc.stdout + proc.stderr, encoding="utf-8", errors="replace")

    result_path = outdir / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    gcode = outdir / f"plate_{plate}.gcode"
    if proc.returncode != 0 or result.get("return_code", 0) != 0 or not gcode.exists():
        reason = result.get("error_string") or f"exit code {proc.returncode}"
        raise SlicerError(f"slicing failed: {reason} (log: {outdir / 'slicer.log'})")
    return SliceResult(project=project, sliced_3mf=sliced, gcode=gcode, result=result, elapsed_s=elapsed,
                       slicer=version(binary) or Path(binary).name, notes=notes)
