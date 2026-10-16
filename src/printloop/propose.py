"""Proposta della patch: a regole (deterministica) o con Gemma, sempre tra i candidati della KB.

Logica del loop a regole: alla prima iterazione si prende il primo candidato utilizzabile e lo si sposta
di un passo. Se il difetto è lo stesso dell'iterazione precedente e la severità è scesa, si insiste sullo
stesso parametro; se non è scesa, si passa al candidato successivo. Il modello, quando c'è, sceglie tra gli
stessi candidati filtrati; il validatore controlla comunque ogni proposta.
"""
from __future__ import annotations

from dataclasses import dataclass

from printloop import kb, llm, project
from printloop.config import LLM
from printloop.models import Change, Diagnosis, Proposal
from printloop.taxonomy import label


@dataclass
class PastStep:
    """Un'iterazione approvata: difetto osservato prima della patch e modifiche applicate."""
    defect: str
    severity: int
    changes: list[Change]


def viable(defect: str, settings: dict, exclude: set[str]) -> list[dict]:
    """Candidati applicabili: presenti nel progetto, non esclusi, con margine nella direzione richiesta.

    Ordine dei sospetti: prima i parametri cambiati dall'utente rispetto al profilo di sistema, poi quelli
    già all'estremo del range nella direzione che peggiora il difetto (es. ugello al massimo con stringing),
    poi l'ordine della KB.
    """
    out = []
    modified = project.modified_keys(settings)
    for cand in kb.candidates(defect):
        if cand.key in exclude:
            continue
        current = project.current_value(settings, cand.key, cand.meta)
        if current is None:
            continue
        lo, hi = kb.bounds(cand.key, settings)
        if (current > hi and cand.sign < 0) or (current < lo and cand.sign > 0):
            target = hi if current > hi else lo  # valore fuori limiti: prima lo si riporta dentro
        else:
            target = min(hi, max(lo, current + cand.sign * cand.step))
        if (target - current) * cand.sign <= 1e-9:
            continue
        real = project.resolve_keys(settings, cand.key, cand.meta)
        # 0 = all'estremo "buono", 1 = all'estremo opposto (quello che peggiora il difetto)
        position = (current - lo) / (hi - lo) if hi > lo else 0.5
        badness = position if cand.sign < 0 else 1 - position
        out.append({"key": cand.key, "label": cand.label, "unit": cand.unit, "direction": cand.direction,
                    "current": current, "step": cand.step, "bounds": [lo, hi], "default_target": round(target, 3),
                    "modified_by_user": any(k in modified for k in real), "at_extreme": badness >= EXTREME})
    return sorted(out, key=lambda o: (not o["modified_by_user"], not o["at_extreme"]))


EXTREME = 0.85  # frazione del range oltre la quale un valore è considerato all'estremo


def _order(options: list[dict], diagnosis: Diagnosis, history: list[PastStep]) -> list[dict]:
    if not history or history[-1].defect != diagnosis.primary:
        return options
    last = history[-1]
    last_keys = {c.key for c in last.changes if not c.companion}
    improved = diagnosis.severity < last.severity
    same = [o for o in options if o["key"] in last_keys]
    other = [o for o in options if o["key"] not in last_keys]
    return same + other if improved else other + same


def propose_rules(diagnosis: Diagnosis, settings: dict, history: list[PastStep], exclude: set[str]) -> Proposal | None:
    options = _order(viable(diagnosis.primary, settings, exclude), diagnosis, history)
    if not options:
        return None
    pick = options[0]
    verb = "aumentare" if pick["direction"] == "up" else "ridurre"
    repeat = bool(history) and history[-1].defect == diagnosis.primary and pick["key"] in {
        c.key for c in history[-1].changes}
    reason = (f"{label(diagnosis.primary)}: {verb} {pick['label'].lower()} di un passo "
              f"({pick['current']:g} → {pick['default_target']:g} {pick['unit']})")
    if repeat:
        reason += "; la severità è scesa con lo stesso parametro, si prosegue nella stessa direzione"
    change = Change(key=pick["key"], after=pick["default_target"], reason=reason)
    return Proposal(defect=diagnosis.primary, changes=[change], source="rules",
                    rationale=f"Primo candidato utilizzabile della knowledge base per '{label(diagnosis.primary)}'.",
                    expected_effect=f"riduzione di: {label(diagnosis.primary).lower()}")


PROPOSE_SYSTEM = """You are the process engineer of PrintLoop. Given a diagnosed FDM print defect, choose the slicer
parameter change most likely to fix its CAUSE, among the candidate parameters provided.
Rules:
- Use only keys from the candidate list, at most 2 changes, moving each in its allowed direction.
- Prefer ONE change, unless two are clearly needed. Keep each change within one step (max two) of the current value.
- Use the history: if a previous change on the same defect did not reduce severity, try a different parameter.
- A parameter the user changed away from the system profile is a strong suspect for the cause.
- reason and rationale must be in Italian, short and concrete; expected_effect describes what should change on the part.
- Answer with JSON only."""


def _schema(keys: list[str]) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "changes": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"key": {"type": "string", "enum": keys}, "value": {"type": "number"},
                               "reason": {"type": "string"}},
                "required": ["key", "value", "reason"]}},
            "rationale": {"type": "string"},
            "expected_effect": {"type": "string"},
        },
        "required": ["changes", "rationale", "expected_effect"],
    }


def propose_llm(diagnosis: Diagnosis, settings: dict, history: list[PastStep], exclude: set[str],
                note: str = "") -> Proposal | None:
    options = viable(diagnosis.primary, settings, exclude)
    if not options:
        return None
    finding = diagnosis.primary_finding()
    lines = [
        f"Defect: {diagnosis.primary} ({label(diagnosis.primary)}), severity {diagnosis.severity}/3, "
        f"confidence {diagnosis.confidence:.2f}",
        f"Evidence: {'; '.join(e.description for e in finding.evidence) if finding else '-'}",
        f"Printer: {project.get_text(settings, 'printer_settings_id')}, material: {project.material(settings)}",
        "Candidates (key | meaning | current | allowed direction | step | bounds | changed by user vs system profile"
        " | current value at the extreme that worsens the defect):",
    ]
    lines += [f"- {o['key']} | {o['label']} | {o['current']:g} {o['unit']} | {o['direction']} | {o['step']:g} | "
              f"{o['bounds'][0]:g}..{o['bounds'][1]:g} | {'yes' if o['modified_by_user'] else 'no'} | "
              f"{'yes' if o['at_extreme'] else 'no'}" for o in options]
    if history:
        lines.append("History of approved patches in this case:")
        lines += [f"- defect {h.defect} severity {h.severity}: " +
                  ", ".join(f"{c.key} {c.before}->{c.after}" for c in h.changes) for h in history]
    if note:
        lines.append(f"Operator note: {note}")
    messages = [{"role": "system", "content": PROPOSE_SYSTEM}, {"role": "user", "content": "\n".join(lines)}]
    raw, latency = llm.chat_json(messages, _schema([o["key"] for o in options]), name="patch")
    changes = [Change(key=c["key"], after=float(c["value"]), reason=str(c.get("reason", "")))
               for c in raw.get("changes") or []]
    return Proposal(defect=diagnosis.primary, changes=changes, source="llm", model=LLM.model,
                    latency_ms=round(latency, 1), rationale=str(raw.get("rationale", "")),
                    expected_effect=str(raw.get("expected_effect", "")))
