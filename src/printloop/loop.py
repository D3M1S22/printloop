"""PrintLoop case and the Mode 2 state machine (docs/printloop/03_ARCHITECTURE.md §3).

photos + 3MF project -> diagnosis -> patch (KB + validator) -> re-slice -> pre-flight -> approval
-> print -> photos of the reprint -> ... until the part is acceptable, or escalation after K patches.

States: awaiting_photos -> ready -> diagnosed -> awaiting_approval -> (approved) awaiting_photos ...
        needs_info (uncertain diagnosis), escalated, done.
The operator can rewind to any earlier step (rewind_targets): files that no longer belong to the case are
moved to discarded/<stamp>/ together with a snapshot of case.json, never deleted.
Every step is appended to runs/cases/<id>/audit.jsonl. Cases are files on disk: no database.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from printloop import detector, diagnose, gcode, kb, llm, preflight, project, propose, slicer, validate
from printloop.config import LOOP
from printloop.models import (Attempt, Case, Change, Confirmation, Decision, Diagnosis, Iteration, PhotoDetection,
                              Proposal, now_iso)
from printloop.taxonomy import label

_LOCK = threading.RLock()
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

# Steps of one iteration, in order. Rewinding to a step puts the case back in the state that waits for it.
STEPS = ("photos", "diagnosis", "patch", "approval")
_POSITION = {"awaiting_photos": 0, "ready": 1, "needs_info": 1, "diagnosed": 2, "awaiting_approval": 3,
             "escalated": len(STEPS), "done": len(STEPS)}
OPEN_STATES = ("awaiting_photos", "ready", "needs_info", "diagnosed", "awaiting_approval")
CONFIRM_STATES = ("awaiting_photos", "ready", "needs_info", "diagnosed")


class CaseError(ValueError):
    """Operation not allowed in the current state of the case."""


class NotFound(KeyError):
    pass


def cases_dir() -> Path:
    path = LOOP.runs_dir / "cases"
    path.mkdir(parents=True, exist_ok=True)
    return path


def case_dir(case_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_id):
        raise NotFound(case_id)
    return cases_dir() / case_id


def _save(case: Case) -> Case:
    case.updated_at = now_iso()
    path = case_dir(case.id) / "case.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return case


def _audit(case: Case, event: str, actor: str = "system", **data: Any) -> None:
    row = {"ts": now_iso(), "case_id": case.id, "iteration": case.current.n if case.iterations else 0,
           "state": case.state, "event": event, "actor": actor, **data}
    with open(case_dir(case.id) / "audit.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load(case_id: str) -> Case:
    path = case_dir(case_id) / "case.json"
    if not path.exists():
        raise NotFound(case_id)
    return Case.model_validate_json(path.read_text(encoding="utf-8"))


def list_cases() -> list[Case]:
    out = []
    for path in sorted(cases_dir().glob("*/case.json")):
        try:
            out.append(Case.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(out, key=lambda c: c.updated_at, reverse=True)


def audit_log(case_id: str) -> list[dict]:
    path = case_dir(case_id) / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _settings(case: Case, rel: str) -> dict:
    return project.read_settings(case_dir(case.id) / rel)


def _require(case: Case, *states: str) -> None:
    if case.state not in states:
        raise CaseError(f"operation not allowed in state '{case.state}' (allowed: {', '.join(states)})")


def _discard(case: Case, paths: list[Path], tag: str, snapshot: str | None = None) -> str | None:
    """Moves files that no longer belong to the case into discarded/<stamp>_<tag>/, keeping relative paths.

    Photos are of physical prints and cannot be recreated: nothing the operator produced is ever deleted,
    only archived. Returns the archive folder (relative to the case) or None if there was nothing to move.
    """
    root = case_dir(case.id)
    paths = [p for p in paths if p.exists()]
    if not paths and snapshot is None:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archive = root / "discarded" / f"{stamp}_{uuid.uuid4().hex[:4]}_{tag}"
    archive.mkdir(parents=True)
    for path in paths:
        target = archive / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
    if snapshot is not None:
        (archive / "case.json").write_text(snapshot, encoding="utf-8")
    return str(archive.relative_to(root))


def _clear(case: Case, it: Iteration, step: str) -> list[Path]:
    """Resets iteration `it` to just before `step` and returns the files that no longer belong to it."""
    root = case_dir(case.id)
    index = STEPS.index(step)
    paths: list[Path] = []
    it.decision = None
    it.confirmed = None
    if index <= STEPS.index("patch"):
        it.proposal = it.validation = it.preflight = None
        it.patched_project = it.sliced_3mf = None
        it.slice = None
        paths += sorted(root.glob(f"iter_{it.n}/attempt_*")) + sorted(root.glob(f"iter_{it.n}/edit_*"))
    if index <= STEPS.index("diagnosis"):
        it.diagnosis = None
        it.rejected = []  # rejections were made against the diagnosis being discarded
    if index == 0:
        it.photos = []
        it.detections = []
        it.note = ""
        paths.append(root / f"iter_{it.n}" / "photos")
    return paths


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else ("es" if noun.endswith("ch") else "s"))


def _rejected_keys(case: Case) -> list[str]:
    return sorted({c.key for it in case.iterations for r in it.rejected
                   for c in Proposal.model_validate(r["proposal"]).changes if not c.companion})


# --- creation --------------------------------------------------------------------------------------------

def create(project_file: str | Path, name: str | None = None) -> Case:
    """New case from a 3MF project (the one that was printed). Runs the reference slice right away."""
    project_file = Path(project_file)
    settings = project.read_settings(project_file)  # validates the 3MF before creating the folder
    case_id = uuid.uuid4().hex[:10]
    root = case_dir(case_id)
    root.mkdir(parents=True)
    shutil.copy(project_file, root / "original.3mf")
    try:
        result = slicer.slice_project(root / "original.3mf", root / "baseline")
    except slicer.SlicerError:
        shutil.rmtree(root, ignore_errors=True)
        raise
    stats = gcode.parse(result.gcode)
    case = Case(
        id=case_id, name=name or project_file.stem,
        printer=project.get_text(settings, "printer_settings_id"),
        material=project.material(settings), process=project.get_text(settings, "print_settings_id"),
        max_iterations=LOOP.max_iterations,
        baseline={**result.summary(), "filament_g": preflight.grams(stats, settings), "gcode": stats.summary()},
        iterations=[Iteration(n=1, project="original.3mf", source_gcode="baseline/plate_1.gcode")],
    )
    _save(case)
    _audit(case, "case_created", project=project_file.name, printer=case.printer, material=case.material,
           slice=result.summary())
    return case


def delete(case_id: str) -> None:
    """Deletes the case with all its files (photos, 3MF, G-code, audit log)."""
    with _LOCK:
        load(case_id)  # 404 if missing
        shutil.rmtree(case_dir(case_id))


# --- photos and diagnosis ------------------------------------------------------------------------------

def add_photos(case_id: str, files: list[tuple[str, bytes]], note: str = "", replace: bool = True) -> Case:
    with _LOCK:
        case = load(case_id)
        _require(case, "awaiting_photos", "ready", "needs_info")
        it = case.current
        photo_dir = case_dir(case.id) / f"iter_{it.n}" / "photos"
        if replace:
            _discard(case, [photo_dir], f"iter{it.n}_replaced_photos")
            it.photos = []
            it.detections = []
        photo_dir.mkdir(parents=True, exist_ok=True)
        if len(it.photos) + len(files) > LOOP.max_photos:
            raise CaseError(f"at most {LOOP.max_photos} photos per iteration")
        for filename, data in files:
            safe = _SAFE.sub("_", Path(filename).name) or "photo.jpg"
            target = photo_dir / safe
            target.write_bytes(data)
            try:
                with Image.open(target) as img:
                    img.verify()
            except Exception as exc:  # noqa: BLE001 - any decoding error
                target.unlink(missing_ok=True)
                raise CaseError(f"{filename}: not a valid image") from exc
            it.photos.append(str(target.relative_to(case_dir(case.id))))
        if note:
            it.note = note
        case.state = "ready"
        _audit(case, "photos_added", actor="operator", photos=it.photos, note=note)
        _detect_photos(case, it)
        return _save(case)


def detector_enabled() -> bool:
    return LOOP.detector and llm.vision_available()


def _detect_photos(case: Case, it: Iteration) -> None:
    """E4B labels for the photos that do not have them yet. Best effort: errors are recorded, never raised."""
    if not detector_enabled():
        return
    done = {d.photo for d in it.detections}
    new = []
    for rel in it.photos:
        if rel in done:
            continue
        det = detector.detect(case_dir(case.id) / rel)
        new.append(PhotoDetection(photo=rel, defects=det.defects, primary=det.primary, model=det.model,
                                  latency_ms=det.latency_ms, error=det.error))
    if new:
        it.detections += new
        _audit(case, "detected", actor="model", detections=[d.model_dump() for d in new])


def _previous_diagnosis(case: Case) -> Diagnosis | None:
    return case.iterations[-2].diagnosis if len(case.iterations) > 1 else None


def diagnose_case(case_id: str, mode: str = "auto", defect: str | None = None, severity: int | None = None,
                  note: str = "") -> Case:
    """Diagnosis of the current iteration. mode: auto (LLM if configured, else operator), llm, operator."""
    with _LOCK:
        case = load(case_id)
        _require(case, "ready", "needs_info", "diagnosed", "awaiting_photos", "awaiting_approval")
        it = case.current
        note = note or it.note
        if mode == "auto":
            mode = "operator" if defect else ("llm" if llm.available() else "operator")
        if mode == "llm":
            if not it.photos:
                raise CaseError("upload photos of the part first")
            photos = [case_dir(case.id) / p for p in it.photos]
            hint = diagnose.detector_hint(it.detections) if LOOP.detector else None
            diag = diagnose.diagnose_llm(photos, case.printer, case.material, note, _previous_diagnosis(case), hint)
        else:
            if defect is None:
                raise CaseError("offline mode: specify the observed defect (defect) and its severity")
            diag = diagnose.diagnose_operator(defect, 2 if severity is None else severity, note, it.photos)
        if LOOP.detector:
            diagnose.apply_detector(diag, it.detections, LOOP.accept_severity)
        _discard(case, _clear(case, it, "patch"), f"iter{it.n}_rediagnosed")
        it.diagnosis = diag
        _audit(case, "diagnosed", actor="model" if diag.source == "llm" else "operator",
               diagnosis=diag.model_dump())
        _route_after_diagnosis(case)
        return _save(case)


def _route(case: Case, it: Iteration) -> tuple[str, str | None, str]:
    """Where the diagnosis of `it` leads: (state, outcome, message). No side effects."""
    diag = it.diagnosis
    assert diag is not None
    patches_applied = it.n - 1
    # The model disagrees with the detector: the operator decides before anything closes or escalates.
    if diag.source == "llm" and diag.detector and diag.detector.agreement == "disagree":
        return "needs_info", None, diag.question_for_operator
    if diag.primary == "none" or diag.severity <= LOOP.accept_severity:
        outcome = "no_defect" if patches_applied == 0 else "fixed"
        message = ("No defect to fix." if patches_applied == 0 else
                   f"Part acceptable after {_count(patches_applied, 'patch')}.")
        return "done", outcome, message
    if diag.source == "llm" and (diag.needs_more_info or diag.confidence < LOOP.min_confidence or diag.primary == "other"):
        if diag.primary == "other":
            return "needs_info", None, "Defect outside the taxonomy: specify it manually or close the case."
        return "needs_info", None, diag.question_for_operator or (
            f"Uncertain diagnosis ({label(diag.primary)}, confidence {diag.confidence:.2f}): "
            "add a closer photo of the defect or specify it manually.")
    if patches_applied >= case.max_iterations:
        return ("escalated", "escalated",
                f"Limit of {case.max_iterations} patches reached with '{label(diag.primary)}' still present.")
    reason = kb.escalation(diag.primary)
    if reason or not kb.candidates(diag.primary):
        return "escalated", "escalated", reason or f"No KB parameter for '{label(diag.primary)}'."
    return "diagnosed", None, f"{label(diag.primary)}, severity {diag.severity}/3."


def _route_after_diagnosis(case: Case) -> None:
    state, outcome, message = _route(case, case.current)
    if state == "escalated":
        _escalate(case, message)
        return
    case.state, case.outcome, case.message = state, outcome, message  # type: ignore[assignment]
    if state == "done":
        _audit(case, "done", outcome=outcome)
    elif state == "needs_info":
        _audit(case, "needs_info", message=message)


def _escalate(case: Case, reason: str, outcome: str = "escalated") -> None:
    case.state = "escalated"
    case.outcome = outcome  # type: ignore[assignment]
    case.message = reason
    _audit(case, "escalated", reason=reason)


# --- proposal, slicing, pre-flight ---------------------------------------------------------------------

def _history(case: Case) -> list[propose.PastStep]:
    steps = []
    for it in case.iterations[:-1]:
        if it.decision and it.decision.approved and it.proposal and it.diagnosis:
            steps.append(propose.PastStep(it.diagnosis.primary, it.diagnosis.severity, it.proposal.changes))
    return steps


def _applied_changes(case: Case) -> list[Change]:
    return [c for step in _history(case) for c in step.changes]


def _build(case: Case, it: Iteration, changes: list[Change], settings: dict, tag: str):
    """Writes the patched project, slices it and runs the pre-flight. Returns (rel_dir, result, preflight)."""
    root = case_dir(case.id)
    rel = Path(f"iter_{it.n}") / tag
    shutil.rmtree(root / rel, ignore_errors=True)
    real = validate.real_map(changes, settings)
    # Every key patched in the case (approved iterations + this one) must be declared as modified against the
    # system preset, otherwise OrcaSlicer resets it to the system value when the user reopens the 3MF.
    marked = {k for c in _applied_changes(case) for k in c.real} | set(real)
    patched_settings, _ = project.mark_different(project.apply_changes(settings, real), marked)
    patched = project.write_patched(root / it.project, root / rel / "patched.3mf", patched_settings)
    result = slicer.slice_project(patched, root / rel / "slice")
    # The slicer CLI writes the list back empty in the exported 3MF: restore it in the delivered file.
    delivered, _ = project.mark_different(project.read_settings(result.sliced_3mf), marked)
    project.rewrite_settings(result.sliced_3mf, delivered)
    before = gcode.parse(root / it.source_gcode)
    after = gcode.parse(result.gcode)
    time_before = _slice_time(root / Path(it.source_gcode).parent)
    report = preflight.run(before, after, changes, settings, patched_settings, time_before, result.print_time_s,
                           delivered_settings=project.read_settings(result.sliced_3mf))
    return rel, result, report


def _slice_time(slice_dir: Path) -> float | None:
    path = slice_dir / "result.json"
    if not path.exists():
        return None
    plates = json.loads(path.read_text()).get("sliced_plates") or [{}]
    return plates[0].get("total_predication")


def propose_case(case_id: str, mode: str = "auto") -> Case:
    """Generates a verified patch. mode: auto (LLM if configured), llm, rules."""
    with _LOCK:
        case = load(case_id)
        _require(case, "diagnosed")
        it = case.current
        assert it.diagnosis is not None
        settings = _settings(case, it.project)
        history = _history(case)
        applied = _applied_changes(case)
        exclude = set(case.rejected_keys)
        use_llm = mode == "llm" or (mode == "auto" and llm.available())
        rejected: list[Attempt] = []

        for attempt in range(1, LOOP.propose_attempts + 1):
            proposal = None
            if use_llm:
                try:
                    proposal = propose.propose_llm(it.diagnosis, settings, history, exclude, it.note)
                except llm.LLMUnavailable as exc:
                    _audit(case, "llm_error", error=str(exc))
                use_llm = False  # after one model attempt, continue with the rules
            if proposal is None:
                proposal = propose.propose_rules(it.diagnosis, settings, history, exclude)
            if proposal is None:
                break
            check, changes = validate.validate(proposal.changes, it.diagnosis.primary, settings, applied)
            if not check.ok:
                rejected.append(Attempt(source=proposal.source, changes=proposal.changes, stage="validation",
                                        reason="; ".join(check.errors)))
                _audit(case, "proposal_rejected", stage="validation", errors=check.errors, source=proposal.source)
                if proposal.source == "rules":
                    exclude |= {c.key for c in proposal.changes}
                continue
            try:
                rel, result, report = _build(case, it, changes, settings, f"attempt_{attempt}")
            except slicer.SlicerError as exc:
                rejected.append(Attempt(source=proposal.source, changes=changes, stage="slicing", reason=str(exc)))
                _audit(case, "proposal_rejected", stage="slicing", error=str(exc))
                exclude |= {c.key for c in changes if not c.companion}
                continue
            if not report.ok:
                failed = [f"{c.key or c.check}: {c.detail}" for c in report.checks + report.limits if c.status == "fail"]
                rejected.append(Attempt(source=proposal.source, changes=changes, stage="preflight",
                                        reason="; ".join(failed)))
                _audit(case, "proposal_rejected", stage="preflight", failed=failed, source=proposal.source)
                exclude |= {c.key for c in changes if not c.companion}
                continue
            proposal.changes = changes
            proposal.rejected_attempts = rejected
            _set_proposal(case, it, proposal, check, report, rel, result)
            _audit(case, "proposed", proposal=proposal.model_dump(), preflight_ok=report.ok,
                   warnings=check.warnings)
            return _save(case)

        it.proposal = Proposal(defect=it.diagnosis.primary, changes=[], rejected_attempts=rejected,
                               rationale="no verifiable patch")
        detail = " Attempts: " + " | ".join(a.reason for a in rejected) if rejected else ""
        _escalate(case, f"No verifiable patch for '{label(it.diagnosis.primary)}' "
                        f"with the KB parameters.{detail}")
        return _save(case)


def _set_proposal(case: Case, it: Iteration, proposal: Proposal, check, report, rel: Path, result) -> None:
    it.proposal, it.validation, it.preflight = proposal, check, report
    it.patched_project = str(rel / "patched.3mf")
    it.sliced_3mf = str(rel / "slice" / result.sliced_3mf.name)
    it.slice = result.summary()
    case.state = "awaiting_approval"
    case.message = APPROVAL_MESSAGE


APPROVAL_MESSAGE = "Patch verified on the G-code: awaiting operator approval."
REPRINT_MESSAGE = "Patch approved: print the patched 3MF and upload photos of the reprint."


# --- operator decision ---------------------------------------------------------------------------------

def decide(case_id: str, approved: bool, reason: str = "", edits: dict[str, float] | None = None,
           stop: bool = False, actor: str = "operator") -> Case:
    """Approval, rejection (with a reason), edited values or stop of the loop by the operator."""
    with _LOCK:
        case = load(case_id)
        _require(case, *OPEN_STATES)
        it = case.current
        if stop:
            it.decision = Decision(approved=False, reason=reason, actor=actor, stop=True)
            _audit(case, "stopped", actor=actor, reason=reason)
            _escalate(case, f"Loop stopped by the operator. {reason}".strip(), outcome="stopped")
            return _save(case)
        _require(case, "awaiting_approval")
        assert it.proposal is not None and it.diagnosis is not None

        if edits:
            settings = _settings(case, it.project)
            changes = [Change(key=k, after=float(v), reason="value chosen by the operator") for k, v in edits.items()]
            check, changes = validate.validate(changes, it.diagnosis.primary, settings, _applied_changes(case),
                                               operator=True)
            if not check.ok:
                raise CaseError("invalid edit: " + "; ".join(check.errors))
            n_edit = len(list((case_dir(case.id) / f"iter_{it.n}").glob("edit_*"))) + 1
            rel, result, report = _build(case, it, changes, settings, f"edit_{n_edit}")
            previous = it.proposal
            proposal = Proposal(defect=previous.defect, changes=changes, source="operator",
                                rationale=reason or "values edited by the operator",
                                expected_effect=previous.expected_effect, rejected_attempts=previous.rejected_attempts)
            _set_proposal(case, it, proposal, check, report, rel, result)
            _audit(case, "proposal_edited", actor=actor, edits=edits, preflight_ok=report.ok, warnings=check.warnings)
            if not approved:
                return _save(case)

        assert it.preflight is not None
        if approved:
            override = not it.preflight.ok
            if override and not reason:
                raise CaseError("the pre-flight did not pass: approving anyway requires a reason")
            it.decision = Decision(approved=True, reason=reason, actor=actor, edited=bool(edits),
                                   override_preflight=override)
            _audit(case, "approved", actor=actor, reason=reason, override_preflight=override,
                   print_file=it.sliced_3mf)
            case.iterations.append(Iteration(n=it.n + 1, project=it.patched_project or it.project,
                                             source_gcode=str(Path(it.sliced_3mf).parent / "plate_1.gcode")))
            case.state = "awaiting_photos"
            case.message = REPRINT_MESSAGE
            return _save(case)

        if not reason:
            raise CaseError("rejecting a patch requires a reason")
        keys = [c.key for c in it.proposal.changes if not c.companion]
        rejected = {"proposal": it.proposal.model_dump(), "reason": reason, "at": now_iso()}
        _discard(case, _clear(case, it, "patch"), f"iter{it.n}_rejected")
        it.rejected.append(rejected)
        case.rejected_keys = _rejected_keys(case)
        case.state = "diagnosed"
        case.message = "Patch rejected: you can ask for a new proposal (rejected parameters are excluded)."
        _audit(case, "rejected", actor=actor, reason=reason, keys=keys)
        return _save(case)


def can_confirm(case: Case) -> bool:
    """The reprint of an approved patch can be confirmed good before a new patch is proposed."""
    return case.state in CONFIRM_STATES and case.current.n > 1


def confirm_success(case_id: str, note: str = "", actor: str = "operator") -> Case:
    """The operator confirms that the reprint is good: the case closes as fixed, photos and diagnosis optional."""
    with _LOCK:
        case = load(case_id)
        if not can_confirm(case):
            raise CaseError("only the reprint of an approved patch can be confirmed, before a new patch is proposed")
        it = case.current
        it.confirmed = Confirmation(note=note, actor=actor)
        patches = it.n - 1
        case.state = "done"
        case.outcome = "fixed"
        case.message = f"Reprint confirmed good by the operator after {_count(patches, 'patch')}." + (
            f" Note: {note}" if note else "")
        _audit(case, "confirmed_success", actor=actor, note=note, patches=patches)
        return _save(case)


# --- rewind --------------------------------------------------------------------------------------------

def _reachable(case: Case, it: Iteration, step: str) -> bool:
    """True if the data of `it` still supports the state that waits for `step`."""
    if step == "photos":
        return True
    if step == "diagnosis":
        return bool(it.photos) or it.diagnosis is not None
    if step == "patch":
        return it.diagnosis is not None and _route(case, it)[0] == "diagnosed"
    return bool(it.proposal and it.proposal.changes and it.preflight and it.sliced_3mf)


def _discards(case: Case, n: int, step: str) -> list[str]:
    """What rewinding to (n, step) throws away, in plain words for the confirmation dialog."""
    it = case.iterations[n - 1]
    index = STEPS.index(step)
    out = []
    if index == 0 and it.photos:
        out.append(f"{_count(len(it.photos), 'photo')} of iteration {n}")
    if index <= 1 and it.diagnosis:
        out.append(f"the diagnosis of iteration {n}")
    if index <= 1 and it.rejected:
        out.append(f"{_count(len(it.rejected), 'rejected proposal')} of iteration {n}")
    if index <= 2 and it.proposal and it.proposal.changes:
        out.append(f"the patch of iteration {n}")
    if it.decision and it.decision.approved:
        out.append(f"the approval of iteration {n}")
    elif it.decision and it.decision.stop:
        out.append("the stop of the loop")
    if it.confirmed:
        out.append("the success confirmation")
    for later in case.iterations[n:]:
        parts = [_count(len(later.photos), "photo")] if later.photos else []
        parts += ["diagnosis"] if later.diagnosis else []
        parts += ["patch"] if later.proposal and later.proposal.changes else []
        if parts:  # an iteration with nothing in it yet is not worth mentioning
            out.append(f"iteration {later.n} ({', '.join(parts)})")
    return out


def rewind_targets(case: Case) -> list[dict]:
    """Earlier steps the case can go back to, oldest first. The last one is "one step back"."""
    current = (case.current.n, _POSITION[case.state])
    targets = []
    for it in case.iterations:
        for index, step in enumerate(STEPS):
            if (it.n, index) < current and _reachable(case, it, step):
                targets.append({"iteration": it.n, "step": step, "discards": _discards(case, it.n, step)})
    return targets


def rewind(case_id: str, iteration: int, step: str, actor: str = "operator") -> Case:
    """Goes back to `step` of `iteration`, discarding everything that came after it."""
    with _LOCK:
        case = load(case_id)
        target = next((t for t in rewind_targets(case) if t["iteration"] == iteration and t["step"] == step), None)
        if target is None:
            raise CaseError(f"cannot go back to '{step}' of iteration {iteration} from state '{case.state}'")
        root = case_dir(case.id)
        snapshot = case.model_dump_json(indent=2)
        paths = [root / f"iter_{later.n}" for later in case.iterations[iteration:]]
        case.iterations = case.iterations[:iteration]
        it = case.current
        paths += _clear(case, it, step)
        archive = _discard(case, paths, f"rewind_iter{iteration}_{step}", snapshot=snapshot)
        case.rejected_keys = _rejected_keys(case)
        case.outcome = None
        if step == "photos":
            case.state = "awaiting_photos"
            case.message = REPRINT_MESSAGE if it.n > 1 else "Upload photos of the printed part."
        elif step == "diagnosis":
            case.state = "ready" if it.photos else "awaiting_photos"
            case.message = "Run the diagnosis again."
        elif step == "patch":
            case.state, _, case.message = _route(case, it)  # type: ignore[assignment]
        else:
            case.state = "awaiting_approval"
            case.message = APPROVAL_MESSAGE
        _audit(case, "rewound", actor=actor, to={"iteration": iteration, "step": step},
               discarded=target["discards"], archive=archive)
        return _save(case)


def file_path(case_id: str, rel: str) -> Path:
    """Path of a case file, preventing escapes from the case folder."""
    root = case_dir(case_id).resolve()
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file():
        raise NotFound(rel)
    return path
