"""Caso PrintLoop e macchina a stati del Modo 2 (docs/printloop/03_ARCHITECTURE.md §3).

foto + progetto 3MF -> diagnosi -> patch (KB + validatore) -> re-slice -> pre-flight -> approvazione
-> stampa -> foto della ristampa -> ... fino a pezzo accettabile, oppure escalation dopo K patch.

Stati: awaiting_photos -> ready -> diagnosed -> awaiting_approval -> (approvata) awaiting_photos ...
       needs_info (diagnosi incerta), escalated, done.
Ogni passo scrive su runs/cases/<id>/audit.jsonl. I casi sono file su disco: niente database.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from printloop import diagnose, gcode, kb, llm, preflight, project, propose, slicer, validate
from printloop.config import LOOP
from printloop.models import Attempt, Case, Change, Decision, Diagnosis, Iteration, Proposal, now_iso
from printloop.taxonomy import label

_LOCK = threading.RLock()
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class CaseError(ValueError):
    """Operazione non ammessa nello stato attuale del caso."""


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
        raise CaseError(f"operazione non ammessa nello stato '{case.state}' (ammessi: {', '.join(states)})")


# --- creazione -----------------------------------------------------------------------------------------

def create(project_file: str | Path, name: str | None = None) -> Case:
    """Nuovo caso da un progetto 3MF (quello stampato). Esegue subito lo slicing di riferimento."""
    project_file = Path(project_file)
    settings = project.read_settings(project_file)  # valida il 3MF prima di creare la cartella
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


# --- foto e diagnosi -----------------------------------------------------------------------------------

def add_photos(case_id: str, files: list[tuple[str, bytes]], note: str = "", replace: bool = True) -> Case:
    with _LOCK:
        case = load(case_id)
        _require(case, "awaiting_photos", "ready", "needs_info")
        it = case.current
        photo_dir = case_dir(case.id) / f"iter_{it.n}" / "photos"
        if replace:
            shutil.rmtree(photo_dir, ignore_errors=True)
            it.photos = []
        photo_dir.mkdir(parents=True, exist_ok=True)
        if len(it.photos) + len(files) > LOOP.max_photos:
            raise CaseError(f"al massimo {LOOP.max_photos} foto per iterazione")
        for filename, data in files:
            safe = _SAFE.sub("_", Path(filename).name) or "photo.jpg"
            target = photo_dir / safe
            target.write_bytes(data)
            try:
                with Image.open(target) as img:
                    img.verify()
            except Exception as exc:  # noqa: BLE001 - qualsiasi errore di decodifica
                target.unlink(missing_ok=True)
                raise CaseError(f"{filename}: non è un'immagine valida") from exc
            it.photos.append(str(target.relative_to(case_dir(case.id))))
        if note:
            it.note = note
        case.state = "ready"
        _audit(case, "photos_added", actor="operator", photos=it.photos, note=note)
        return _save(case)


def _previous_diagnosis(case: Case) -> Diagnosis | None:
    return case.iterations[-2].diagnosis if len(case.iterations) > 1 else None


def diagnose_case(case_id: str, mode: str = "auto", defect: str | None = None, severity: int | None = None,
                  note: str = "") -> Case:
    """Diagnosi dell'iterazione corrente. mode: auto (LLM se configurato, altrimenti operatore), llm, operator."""
    with _LOCK:
        case = load(case_id)
        _require(case, "ready", "needs_info", "diagnosed", "awaiting_photos", "awaiting_approval")
        it = case.current
        note = note or it.note
        if mode == "auto":
            mode = "operator" if defect else ("llm" if llm.available() else "operator")
        if mode == "llm":
            if not it.photos:
                raise CaseError("caricare prima le foto del pezzo")
            photos = [case_dir(case.id) / p for p in it.photos]
            diag = diagnose.diagnose_llm(photos, case.printer, case.material, note, _previous_diagnosis(case))
        else:
            if defect is None:
                raise CaseError("modalità offline: indicare il difetto osservato (defect) e la severità")
            diag = diagnose.diagnose_operator(defect, 2 if severity is None else severity, note, it.photos)
        it.diagnosis = diag
        it.proposal = it.validation = it.preflight = None
        it.patched_project = it.sliced_3mf = None
        it.slice = None
        _audit(case, "diagnosed", actor="model" if diag.source == "llm" else "operator",
               diagnosis=diag.model_dump())
        _route_after_diagnosis(case)
        return _save(case)


def _route_after_diagnosis(case: Case) -> None:
    it = case.current
    diag = it.diagnosis
    assert diag is not None
    patches_applied = it.n - 1
    if diag.primary == "none" or diag.severity <= LOOP.accept_severity:
        case.state = "done"
        case.outcome = "no_defect" if patches_applied == 0 else "fixed"
        case.message = ("Nessun difetto da correggere." if patches_applied == 0 else
                        f"Pezzo accettabile dopo {patches_applied} patch.")
        _audit(case, "done", outcome=case.outcome)
        return
    if diag.source == "llm" and (diag.needs_more_info or diag.confidence < LOOP.min_confidence or diag.primary == "other"):
        case.state = "needs_info"
        case.message = diag.question_for_operator or (
            f"Diagnosi incerta ({label(diag.primary)}, confidenza {diag.confidence:.2f}): "
            "aggiungere una foto più ravvicinata del difetto o indicarlo a mano.")
        if diag.primary == "other":
            case.message = "Difetto fuori tassonomia: indicarlo a mano o chiudere il caso."
        _audit(case, "needs_info", message=case.message)
        return
    if patches_applied >= case.max_iterations:
        _escalate(case, f"Limite di {case.max_iterations} patch raggiunto con '{label(diag.primary)}' ancora presente.")
        return
    reason = kb.escalation(diag.primary)
    if reason or not kb.candidates(diag.primary):
        _escalate(case, reason or f"Nessun parametro della KB per '{label(diag.primary)}'.")
        return
    case.state = "diagnosed"
    case.message = f"{label(diag.primary)}, severità {diag.severity}/3."


def _escalate(case: Case, reason: str, outcome: str = "escalated") -> None:
    case.state = "escalated"
    case.outcome = outcome  # type: ignore[assignment]
    case.message = reason
    _audit(case, "escalated", reason=reason)


# --- proposta, slicing, pre-flight ---------------------------------------------------------------------

def _history(case: Case) -> list[propose.PastStep]:
    steps = []
    for it in case.iterations[:-1]:
        if it.decision and it.decision.approved and it.proposal and it.diagnosis:
            steps.append(propose.PastStep(it.diagnosis.primary, it.diagnosis.severity, it.proposal.changes))
    return steps


def _applied_changes(case: Case) -> list[Change]:
    return [c for step in _history(case) for c in step.changes]


def _build(case: Case, it: Iteration, changes: list[Change], settings: dict, tag: str):
    """Scrive il progetto patchato, esegue lo slicing e il pre-flight. Restituisce (rel_dir, result, preflight)."""
    root = case_dir(case.id)
    rel = Path(f"iter_{it.n}") / tag
    shutil.rmtree(root / rel, ignore_errors=True)
    patched_settings = project.apply_changes(settings, validate.real_map(changes, settings))
    patched = project.write_patched(root / it.project, root / rel / "patched.3mf", patched_settings)
    result = slicer.slice_project(patched, root / rel / "slice")
    before = gcode.parse(root / it.source_gcode)
    after = gcode.parse(result.gcode)
    time_before = _slice_time(root / Path(it.source_gcode).parent)
    report = preflight.run(before, after, changes, settings, patched_settings, time_before, result.print_time_s)
    return rel, result, report


def _slice_time(slice_dir: Path) -> float | None:
    path = slice_dir / "result.json"
    if not path.exists():
        return None
    plates = json.loads(path.read_text()).get("sliced_plates") or [{}]
    return plates[0].get("total_predication")


def propose_case(case_id: str, mode: str = "auto") -> Case:
    """Genera una patch verificata. mode: auto (LLM se configurato), llm, rules."""
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
                use_llm = False  # dopo un tentativo del modello si prosegue a regole
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
                               rationale="nessuna patch verificabile")
        detail = " Tentativi: " + " | ".join(a.reason for a in rejected) if rejected else ""
        _escalate(case, f"Nessuna patch verificabile per '{label(it.diagnosis.primary)}' "
                        f"con i parametri della KB.{detail}")
        return _save(case)


def _set_proposal(case: Case, it: Iteration, proposal: Proposal, check, report, rel: Path, result) -> None:
    it.proposal, it.validation, it.preflight = proposal, check, report
    it.patched_project = str(rel / "patched.3mf")
    it.sliced_3mf = str(rel / "slice" / result.sliced_3mf.name)
    it.slice = result.summary()
    case.state = "awaiting_approval"
    case.message = "Patch verificata sul G-code: in attesa dell'approvazione dell'operatore."


# --- decisione dell'operatore --------------------------------------------------------------------------

def decide(case_id: str, approved: bool, reason: str = "", edits: dict[str, float] | None = None,
           stop: bool = False, actor: str = "operator") -> Case:
    """Approvazione, rifiuto (con motivo), modifica dei valori o stop del loop da parte dell'operatore."""
    with _LOCK:
        case = load(case_id)
        _require(case, "awaiting_approval", "diagnosed", "needs_info", "ready", "awaiting_photos")
        it = case.current
        if stop:
            it.decision = Decision(approved=False, reason=reason, actor=actor, stop=True)
            _audit(case, "stopped", actor=actor, reason=reason)
            _escalate(case, f"Loop fermato dall'operatore. {reason}".strip(), outcome="stopped")
            return _save(case)
        _require(case, "awaiting_approval")
        assert it.proposal is not None and it.diagnosis is not None

        if edits:
            settings = _settings(case, it.project)
            changes = [Change(key=k, after=float(v), reason="valore scelto dall'operatore") for k, v in edits.items()]
            check, changes = validate.validate(changes, it.diagnosis.primary, settings, _applied_changes(case),
                                               operator=True)
            if not check.ok:
                raise CaseError("modifica non valida: " + "; ".join(check.errors))
            n_edit = len(list((case_dir(case.id) / f"iter_{it.n}").glob("edit_*"))) + 1
            rel, result, report = _build(case, it, changes, settings, f"edit_{n_edit}")
            previous = it.proposal
            proposal = Proposal(defect=previous.defect, changes=changes, source="operator",
                                rationale=reason or "valori modificati dall'operatore",
                                expected_effect=previous.expected_effect, rejected_attempts=previous.rejected_attempts)
            _set_proposal(case, it, proposal, check, report, rel, result)
            _audit(case, "proposal_edited", actor=actor, edits=edits, preflight_ok=report.ok, warnings=check.warnings)
            if not approved:
                return _save(case)

        assert it.preflight is not None
        if approved:
            override = not it.preflight.ok
            if override and not reason:
                raise CaseError("il pre-flight non è superato: per approvare comunque serve una motivazione")
            it.decision = Decision(approved=True, reason=reason, actor=actor, edited=bool(edits),
                                   override_preflight=override)
            _audit(case, "approved", actor=actor, reason=reason, override_preflight=override,
                   print_file=it.sliced_3mf)
            case.iterations.append(Iteration(n=it.n + 1, project=it.patched_project or it.project,
                                             source_gcode=str(Path(it.sliced_3mf).parent / "plate_1.gcode")))
            case.state = "awaiting_photos"
            case.message = "Patch approvata: stampare il 3MF patchato e caricare le foto della ristampa."
            return _save(case)

        if not reason:
            raise CaseError("per rifiutare una patch serve una motivazione")
        keys = [c.key for c in it.proposal.changes if not c.companion]
        it.rejected.append({"proposal": it.proposal.model_dump(), "reason": reason, "at": now_iso()})
        case.rejected_keys = sorted(set(case.rejected_keys) | set(keys))
        it.proposal = it.validation = it.preflight = None
        it.patched_project = it.sliced_3mf = None
        it.slice = None
        case.state = "diagnosed"
        case.message = "Patch rifiutata: si può chiedere una nuova proposta (esclude i parametri rifiutati)."
        _audit(case, "rejected", actor=actor, reason=reason, keys=keys)
        return _save(case)


def file_path(case_id: str, rel: str) -> Path:
    """Percorso di un file del caso, impedendo l'uscita dalla cartella."""
    root = case_dir(case_id).resolve()
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file():
        raise NotFound(rel)
    return path
