"""Wrapper della CLI di BambuStudio / OrcaSlicer (stessa interfaccia: --slice, --export-3mf, --outputdir).

Verificato headless (nessun display) su BambuStudio 2.8.2 e OrcaSlicer 2.4.2 AppImage: con `--outputdir`
lo slicer scrive `plate_<n>.gcode` e `result.json` accanto al 3MF esportato.

Ogni slicer riscrive il progetto nel proprio formato: un progetto OrcaSlicer riesportato da BambuStudio
perde le impostazioni che esistono solo in Orca (es. chamber_temperature) e non si riapre fedelmente.
Per questo il progetto si lavora con lo slicer che l'ha creato (tag `OrcaSlicer` nei metadati del 3MF).
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
    """Ricava il tempo stimato (secondi) dall'intestazione del G-code se result.json non lo riporta."""
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
    project: Path       # 3MF in ingresso
    sliced_3mf: Path    # 3MF con G-code, pronto per la stampa
    gcode: Path
    result: dict        # result.json dello slicer
    elapsed_s: float
    slicer: str = ""    # versione dello slicer usato
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
    """"orca" se il 3MF porta il tag OrcaSlicer nei metadati, altrimenti "bambu"."""
    try:
        with zipfile.ZipFile(project) as zf:
            model = zf.read("3D/3dmodel.model").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile, OSError):
        return "bambu"
    return "orca" if 'name="OrcaSlicer"' in model else "bambu"


def choose(project: str | Path) -> tuple[str, list[str]]:
    """Slicer per il progetto: SLICER_BIN se impostato, poi quello che l'ha creato, poi l'altro con un avviso."""
    forced = slicer_bin() if _forced() else None
    if forced:
        return forced, []
    origin = project_origin(project)
    bins = slicer_bins()
    if origin in bins:
        return bins[origin], []
    other = next(iter(bins.values()), None)
    if other is None:
        raise SlicerError("slicer non trovato: installare OrcaSlicer o BambuStudio, oppure impostare SLICER_BIN")
    name = {"orca": "OrcaSlicer", "bambu": "BambuStudio"}[origin]
    return other, [f"Progetto creato con {name}, che non è installato: lo slicing usa {Path(other).name} e "
                   "alcune impostazioni specifiche potrebbero non essere rispettate."]


def _forced() -> bool:
    return bool(os.getenv("SLICER_BIN"))


@lru_cache(maxsize=4)
def version(binary: str | None = None) -> str | None:
    binary = binary or slicer_bin()
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
        raise SlicerError(f"slicing oltre {timeout_s} s") from exc
    elapsed = time.perf_counter() - t0
    (outdir / "slicer.log").write_text(proc.stdout + proc.stderr, encoding="utf-8", errors="replace")

    result_path = outdir / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    gcode = outdir / f"plate_{plate}.gcode"
    if proc.returncode != 0 or result.get("return_code", 0) != 0 or not gcode.exists():
        reason = result.get("error_string") or f"exit code {proc.returncode}"
        raise SlicerError(f"slicing fallito: {reason} (log: {outdir / 'slicer.log'})")
    return SliceResult(project=project, sliced_3mf=sliced, gcode=gcode, result=result, elapsed_s=elapsed,
                       slicer=version(binary) or Path(binary).name, notes=notes)
