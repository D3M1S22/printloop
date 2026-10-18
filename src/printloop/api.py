"""JSON API for the React/Vite UI. Run with: `uv run uvicorn printloop.api:app --port 8788 --reload`.

Contracts: docs/printloop/05_API.md. Interactive docs at /docs.
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
from printloop.config import LLM, LOOP, MODE1, ROOT, VISION_LLM, slicer_bins
from printloop.live import monitor as live
from printloop.models import Case, LiveSession
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


def allowed_actions(case: Case) -> list[str]:
    """Buttons the UI shows for the case. `delete` is always allowed and is not listed."""
    actions = list(ACTIONS[case.state])
    if loop.can_confirm(case):
        actions.append("confirm_success")
    if loop.rewind_targets(case):
        actions.append("rewind")
    return actions


def edit_options(case: Case) -> list[dict]:
    """Parameters the operator can edit for the current defect, with resolved bounds and current value."""
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
    """Case + fields derived for the UI: allowed actions, file URLs, labels, rewind targets."""
    data = case.model_dump()
    base = f"/api/cases/{case.id}/files/"
    data["allowed_actions"] = allowed_actions(case)
    data["rewind_targets"] = loop.rewind_targets(case)
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
        raise HTTPException(404, f"case {case_id} not found") from exc


def _run(fn, *args, **kwargs) -> dict:
    with _lock:
        try:
            return view(fn(*args, **kwargs))
        except loop.NotFound as exc:
            raise HTTPException(404, f"not found: {exc}") from exc
        except (loop.CaseError, ProjectError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except slicer.SlicerError as exc:
            raise HTTPException(502, f"slicer: {exc}") from exc
        except llm.LLMUnavailable as exc:
            raise HTTPException(503, f"LLM unavailable: {exc}") from exc


class DiagnoseRequest(BaseModel):
    mode: Literal["auto", "llm", "operator"] = "auto"
    defect: str | None = Field(None, description="Required in operator mode")
    severity: int | None = Field(None, ge=0, le=3)
    note: str = ""


class ProposeRequest(BaseModel):
    mode: Literal["auto", "llm", "rules"] = "auto"


class DecisionRequest(BaseModel):
    approved: bool = False
    reason: str = ""
    edits: dict[str, float] | None = Field(None, description="KB key -> new value chosen by the operator")
    stop: bool = False
    actor: str = "operator"


class ConfirmRequest(BaseModel):
    note: str = ""
    actor: str = "operator"


class RewindRequest(BaseModel):
    iteration: int = Field(..., ge=1)
    step: Literal["photos", "diagnosis", "patch", "approval"]
    actor: str = "operator"


def _warnings() -> list[str]:
    out = []
    if VISION_LLM.enabled and LLM.enabled and VISION_LLM.base_url == LLM.base_url:
        out.append("The detector and the 26B share one server: on a llama.cpp router that keeps one model loaded, "
                   "every switch reloads a model (tens of seconds). Give the detector its own server for Mode 1.")
    return out


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "llm": llm.describe(), "telemetry": llm.TELEMETRY.snapshot(),
            "vision_llm": llm.describe_vision(), "vision_telemetry": llm.VISION_TELEMETRY.snapshot(),
            "mode2_detector": loop.detector_enabled(), "warnings": _warnings(),
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
             "defect": c.current.diagnosis.primary if c.current.diagnosis else None,
             "allowed_actions": allowed_actions(c)} for c in loop.list_cases()]


@app.post("/api/cases")
def create_case(project: UploadFile = File(..., description="The printed 3MF project"), name: str = Form("")) -> dict:
    if not (project.filename or "").lower().endswith(".3mf"):
        raise HTTPException(422, "a BambuStudio/OrcaSlicer .3mf project is required")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(project.filename).name
        with open(path, "wb") as fh:
            shutil.copyfileobj(project.file, fh)
        return _run(loop.create, path, name or None)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return view(_get(case_id))


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: str) -> dict:
    with _lock:
        try:
            loop.delete(case_id)
        except loop.NotFound as exc:
            raise HTTPException(404, f"case {case_id} not found") from exc
    return {"deleted": case_id}


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


@app.post("/api/cases/{case_id}/confirm")
def confirm(case_id: str, req: ConfirmRequest | None = None) -> dict:
    req = req or ConfirmRequest()
    return _run(loop.confirm_success, case_id, req.note, req.actor)


@app.post("/api/cases/{case_id}/rewind")
def rewind(case_id: str, req: RewindRequest) -> dict:
    return _run(loop.rewind, case_id, req.iteration, req.step, req.actor)


@app.get("/api/cases/{case_id}/audit")
def audit(case_id: str) -> list[dict]:
    _get(case_id)
    return loop.audit_log(case_id)


@app.get("/api/cases/{case_id}/files/{rel:path}")
def case_file(case_id: str, rel: str) -> FileResponse:
    try:
        path = loop.file_path(case_id, rel)
    except loop.NotFound as exc:
        raise HTTPException(404, "file not found") from exc
    if path.suffix == ".3mf":  # descriptive download name: printloop_<case>_iter_1_attempt_1_sliced.3mf
        return FileResponse(path, filename=f"printloop_{case_id}_{rel.replace('/slice/', '_').replace('/', '_')}")
    return FileResponse(path)


# --- Mode 1: live monitoring (docs/printloop/08_MODE1_LIVE.md) ------------------------------------------------

class LiveStartRequest(BaseModel):
    source: Literal["replay", "p1s", "url"] | None = None
    replay_dir: str | None = None
    url: str | None = None
    interval_s: float | None = Field(None, ge=1, le=600)
    case_id: str | None = None
    record_all: bool | None = None


class LiveDismissRequest(BaseModel):
    reason: str = ""


class LiveAttachRequest(BaseModel):
    case_id: str | None = None
    session_id: str | None = None
    frames: list[str] | None = None


def live_view(session: LiveSession | None, with_detections: bool = False) -> dict | None:
    if session is None:
        return None
    data = session.model_dump()
    base = f"/api/live/frames/{session.id}/"
    if session.last:
        data["last"]["frame_url"] = base + session.last.frame_id
    for alert_view, alert in zip(data["alerts"], session.alerts):
        alert_view["frame_urls"] = [base + f for f in alert.frames]
    if with_detections:
        data["detections"] = live.detections(session.id)
    return data


def _live(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:  # LiveError, or a frame source that cannot be opened
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, f"not found: {exc}") from exc


@app.get("/api/live")
def live_state() -> dict:
    return {"session": live_view(live.MONITOR.snapshot()), "running": live.MONITOR.running,
            "detector": llm.describe_vision(),
            "printer": {"configured": bool(MODE1.printer_ip and MODE1.printer_access_code), "linked": False},
            "defaults": {"source": MODE1.source, "replay_dir": MODE1.replay_dir, "interval_s": MODE1.interval_s,
                         "snapshot_url": MODE1.snapshot_url}}


@app.post("/api/live/start")
def live_start(req: LiveStartRequest) -> dict:
    if req.case_id:
        _get(req.case_id)
    return live_view(_live(live.MONITOR.start, req.source, req.replay_dir, req.url, req.interval_s, req.case_id,
                           req.record_all))


@app.post("/api/live/stop")
def live_stop() -> dict:
    return live_view(_live(live.MONITOR.stop))


@app.post("/api/live/alerts/{alert_id}/dismiss")
def live_dismiss(alert_id: str, req: LiveDismissRequest | None = None) -> dict:
    return live_view(_live(live.MONITOR.dismiss, alert_id, (req or LiveDismissRequest()).reason))


@app.post("/api/live/pause")
def live_pause() -> dict:
    raise HTTPException(409, "pausing over MQTT is not implemented yet: pause the print on the printer")


@app.post("/api/live/attach")
def live_attach(req: LiveAttachRequest) -> dict:
    """Evidence frames of a session -> photos of the current iteration of a case (default: the linked case)."""
    current = live.MONITOR.snapshot()
    session_id = req.session_id or (current.id if current else None)
    if not session_id:
        raise HTTPException(409, "no live session")
    session = current if current and current.id == session_id else _live(live.load_session, session_id)
    case_id = req.case_id or session.case_id
    if not case_id:
        raise HTTPException(409, "pick the case to attach the evidence to")
    files = _live(live.MONITOR.evidence, session_id, req.frames)
    return _run(loop.add_photos, case_id, files, f"Mode 1 evidence (live session {session_id})")


@app.get("/api/live/sessions")
def live_sessions() -> list[dict]:
    return [{"id": s.id, "status": s.status, "source": s.source, "started_at": s.started_at, "ended_at": s.ended_at,
             "case_id": s.case_id, "frames": s.counts.get("frames", 0),
             "alerts": [{"defect": a.defect, "level": a.level} for a in s.alerts]} for s in live.list_sessions()]


@app.get("/api/live/sessions/{session_id}")
def live_session(session_id: str, detections: bool = False) -> dict:
    return live_view(_live(live.load_session, session_id), with_detections=detections)


@app.delete("/api/live/sessions/{session_id}")
def live_delete(session_id: str) -> dict:
    _live(live.delete_session, live.MONITOR, session_id)
    return {"deleted": session_id}


@app.get("/api/live/frames/{session_id}/{frame_id}")
def live_frame(session_id: str, frame_id: str) -> FileResponse:
    return FileResponse(_live(live.frame_path, session_id, frame_id), media_type="image/jpeg")


# The frontend build (web/dist) is served by the same app: one process is enough for the demo. SPA fallback.
_DIST = ROOT / "web" / "dist"


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or not (_DIST / "index.html").exists():
        raise HTTPException(404, "not found")
    target = (_DIST / full_path).resolve()
    if full_path and _DIST.resolve() in target.parents and target.is_file():
        return FileResponse(target)
    return FileResponse(_DIST / "index.html")
