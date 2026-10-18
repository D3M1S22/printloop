"""API JSON per la UI React/Vite. Avvio: `uv run uvicorn printloop.api:app --port 8788 --reload`.

Contratti: docs/printloop/05_API.md. Documentazione interattiva su /docs.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from printloop import __version__, kb, llm, loop, project, slicer
from printloop.config import LOOP, ROOT, slicer_bins
from printloop.models import Case
from printloop.project import ProjectError
from printloop.taxonomy import DEFECTS, SEVERITY, label

app = FastAPI(title="PrintLoop API", version=__version__,
              description="Photo-based 3D print defect diagnosis (Gemma 4 on AMD) with G-code-verified preset patches.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_lock = threading.Lock()

ACTIONS = {
    "awaiting_photos": ["upload_photos", "diagnose_operator", "stop"],
    "ready": ["diagnose", "upload_photos", "stop"],
    "needs_info": ["upload_photos", "diagnose", "stop"],
    "diagnosed": ["propose", "diagnose", "stop"],
    "awaiting_approval": ["approve", "reject", "edit", "diagnose", "stop"],
    "escalated": [],
    "done": [],
}


def edit_options(case: Case) -> list[dict]:
    """Parametri che l'operatore può modificare per il difetto corrente, con limiti risolti e valore attuale."""
    it = case.current
    if case.state != "awaiting_approval" or not it.diagnosis:
        return []
    settings = project.read_settings(loop.case_dir(case.id) / it.project)
    proposed = {c.key: c.after for c in (it.proposal.changes if it.proposal else []) if not c.companion}
    options = []
    for cand in kb.candidates(it.diagnosis.primary):
        current = project.current_value(settings, cand.key, cand.meta)
        if current is None:
            continue
        lo, hi = kb.bounds(cand.key, settings)
        options.append({"key": cand.key, "label": cand.label, "unit": cand.unit, "step": cand.step,
                        "direction": cand.direction, "min": lo, "max": hi, "current": current,
                        "proposed": proposed.get(cand.key)})
    return options


def view(case: Case) -> dict:
    """Caso + campi derivati per la UI: azioni ammesse, URL dei file, etichette."""
    data = case.model_dump()
    base = f"/api/cases/{case.id}/files/"
    data["allowed_actions"] = ACTIONS[case.state]
    data["llm_mode"] = llm.describe()["mode"]
    for it_view, it in zip(data["iterations"], case.iterations):
        it_view["photo_urls"] = [base + p for p in it.photos]
        it_view["print_file_url"] = base + it.sliced_3mf if it.sliced_3mf else None
        it_view["project_url"] = base + it.project
        if it.diagnosis:
            it_view["diagnosis"]["primary_label"] = label(it.diagnosis.primary)
            it_view["diagnosis"]["severity"] = it.diagnosis.severity
            it_view["diagnosis"]["confidence"] = it.diagnosis.confidence
    approved = [it for it in case.iterations if it.decision and it.decision.approved and it.sliced_3mf]
    data["latest_print_file_url"] = base + approved[-1].sliced_3mf if approved else None
    data["edit_options"] = edit_options(case)
    return data


def _get(case_id: str) -> Case:
    try:
        return loop.load(case_id)
    except loop.NotFound as exc:
        raise HTTPException(404, f"caso {case_id} non trovato") from exc


def _run(fn, *args, **kwargs) -> dict:
    with _lock:
        try:
            return view(fn(*args, **kwargs))
        except loop.NotFound as exc:
            raise HTTPException(404, f"non trovato: {exc}") from exc
        except (loop.CaseError, ProjectError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except slicer.SlicerError as exc:
            raise HTTPException(502, f"slicer: {exc}") from exc
        except llm.LLMUnavailable as exc:
            raise HTTPException(503, f"LLM non disponibile: {exc}") from exc


class DiagnoseRequest(BaseModel):
    mode: Literal["auto", "llm", "operator"] = "auto"
    defect: str | None = Field(None, description="Obbligatorio in modalità operator")
    severity: int | None = Field(None, ge=0, le=3)
    note: str = ""


class ProposeRequest(BaseModel):
    mode: Literal["auto", "llm", "rules"] = "auto"


class DecisionRequest(BaseModel):
    approved: bool = False
    reason: str = ""
    edits: dict[str, float] | None = Field(None, description="Chiave KB -> nuovo valore scelto dall'operatore")
    stop: bool = False
    actor: str = "operator"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "llm": llm.describe(), "telemetry": llm.TELEMETRY.snapshot(),
            "slicer": {"available": slicer.available(), "version": slicer.version(),
                       "installed": {k: slicer.version(b) for k, b in slicer_bins().items()}},
            "max_iterations": LOOP.max_iterations, "min_confidence": LOOP.min_confidence}


@app.get("/api/taxonomy")
def taxonomy() -> dict:
    return {"defects": [{"id": k, **v, "fixable": bool(kb.candidates(k))} for k, v in DEFECTS.items()],
            "severity": SEVERITY}


@app.get("/api/kb")
def knowledge_base() -> dict:
    return kb.load()


@app.get("/api/cases")
def list_cases() -> list[dict]:
    return [{"id": c.id, "name": c.name, "state": c.state, "outcome": c.outcome, "iteration": c.current.n,
             "printer": c.printer, "material": c.material, "updated_at": c.updated_at,
             "defect": c.current.diagnosis.primary if c.current.diagnosis else None} for c in loop.list_cases()]


@app.post("/api/cases")
def create_case(project: UploadFile = File(..., description="Progetto 3MF stampato"), name: str = Form("")) -> dict:
    if not (project.filename or "").lower().endswith(".3mf"):
        raise HTTPException(422, "serve un progetto .3mf di BambuStudio/OrcaSlicer")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(project.filename).name
        with open(path, "wb") as fh:
            shutil.copyfileobj(project.file, fh)
        return _run(loop.create, path, name or None)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return view(_get(case_id))


@app.post("/api/cases/{case_id}/photos")
def upload_photos(case_id: str, photos: list[UploadFile] = File(...), note: str = Form("")) -> dict:
    files = [(p.filename or "photo.jpg", p.file.read()) for p in photos]
    return _run(loop.add_photos, case_id, files, note)


@app.post("/api/cases/{case_id}/diagnose")
def diagnose(case_id: str, req: DiagnoseRequest) -> dict:
    return _run(loop.diagnose_case, case_id, req.mode, req.defect, req.severity, req.note)


@app.post("/api/cases/{case_id}/propose")
def propose(case_id: str, req: ProposeRequest | None = None) -> dict:
    return _run(loop.propose_case, case_id, (req or ProposeRequest()).mode)


@app.post("/api/cases/{case_id}/decision")
def decision(case_id: str, req: DecisionRequest) -> dict:
    return _run(loop.decide, case_id, req.approved, req.reason, req.edits, req.stop, req.actor)


@app.get("/api/cases/{case_id}/audit")
def audit(case_id: str) -> list[dict]:
    _get(case_id)
    return loop.audit_log(case_id)


@app.get("/api/cases/{case_id}/files/{rel:path}")
def case_file(case_id: str, rel: str) -> FileResponse:
    try:
        path = loop.file_path(case_id, rel)
    except loop.NotFound as exc:
        raise HTTPException(404, "file non trovato") from exc
    if path.suffix == ".3mf":  # nome parlante per il download: printloop_<caso>_iter_1_attempt_1_sliced.3mf
        return FileResponse(path, filename=f"printloop_{case_id}_{rel.replace('/slice/', '_').replace('/', '_')}")
    return FileResponse(path)


# Build del frontend (web/dist) servita dalla stessa app: in demo basta un processo. Fallback SPA su index.html.
_DIST = ROOT / "web" / "dist"


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or not (_DIST / "index.html").exists():
        raise HTTPException(404, "non trovato")
    target = (_DIST / full_path).resolve()
    if full_path and _DIST.resolve() in target.parents and target.is_file():
        return FileResponse(target)
    return FileResponse(_DIST / "index.html")
