"""Wrapper della CLI di BambuStudio / OrcaSlicer (stessa interfaccia: --slice, --export-3mf, --outputdir).

Verificato su BambuStudio 2.8.2 headless (nessun display necessario): con `--outputdir` lo slicer scrive
`plate_<n>.gcode` e `result.json` accanto al 3MF esportato.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from printloop.config import slicer_bin


class SlicerError(RuntimeError):
    pass


@dataclass
class SliceResult:
    project: Path       # 3MF in ingresso
    sliced_3mf: Path    # 3MF con G-code, pronto per la stampa
    gcode: Path
    result: dict        # result.json dello slicer
    elapsed_s: float

    @property
    def print_time_s(self) -> float | None:
        plates = self.result.get("sliced_plates") or [{}]
        return plates[0].get("total_predication")

    def summary(self) -> dict:
        return {"sliced_3mf": self.sliced_3mf.name, "gcode": self.gcode.name,
                "print_time_s": self.print_time_s, "slice_elapsed_s": round(self.elapsed_s, 2)}


def available() -> bool:
    return slicer_bin() is not None


@lru_cache(maxsize=1)
def version() -> str | None:
    binary = slicer_bin()
    if not binary:
        return None
    try:
        # cwd temporanea: anche con --help lo slicer scrive result.json nella cartella corrente
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=60, cwd=tmp)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in (out.stdout + out.stderr).splitlines():
        if not line.startswith("[") and ("BambuStudio-" in line or "OrcaSlicer" in line):
            return line.strip().rstrip(":")
    return Path(binary).name


def slice_project(project: str | Path, outdir: str | Path, plate: int = 1, timeout_s: int = 600) -> SliceResult:
    """Esegue lo slicing di una piastra del progetto e restituisce G-code e 3MF stampabile."""
    binary = slicer_bin()
    if not binary:
        raise SlicerError("slicer non trovato: installare OrcaSlicer o BambuStudio, oppure impostare SLICER_BIN")
    project, outdir = Path(project), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sliced = outdir / "sliced.3mf"
    cmd = [binary, str(project.resolve()), "--slice", str(plate), "--export-3mf", sliced.name,
           "--outputdir", str(outdir.resolve())]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise SlicerError(f"slicing oltre {timeout_s} s") from exc
    elapsed = time.perf_counter() - t0
    (outdir / "slicer.log").write_text(proc.stdout + proc.stderr, encoding="utf-8", errors="replace")

    result_path = outdir / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    gcode = outdir / f"plate_{plate}.gcode"
    if proc.returncode != 0 or result.get("return_code", 0) != 0 or not gcode.exists():
        reason = result.get("error_string") or f"exit code {proc.returncode}"
        raise SlicerError(f"slicing fallito: {reason} (log: {outdir / 'slicer.log'})")
    return SliceResult(project=project, sliced_3mf=sliced, gcode=gcode, result=result, elapsed_s=elapsed)
