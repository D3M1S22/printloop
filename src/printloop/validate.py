"""Deterministic patch validator (docs/printloop/03_ARCHITECTURE.md §4.3).

Rules: keys among the KB candidates for the defect, at most LOOP.max_changes changes, KB direction,
step ≤ 2× the KB step, values within bounds (including material bounds), no oscillation against
already approved iterations. Operator choices may exceed step, direction and oscillation (with a
warning), never the bounds.
"""
from __future__ import annotations

from printloop import kb, project
from printloop.config import LOOP
from printloop.models import Change, Validation

EPS = 1e-9


def real_changes(change: Change, settings: dict) -> dict[str, float | str]:
    """Translates a KB change into the real project keys."""
    if change.companion:
        return {change.key: change.after}
    meta = kb.param(change.key)
    keys = project.resolve_keys(settings, change.key, meta)
    if meta.get("alias") == "bed_temperature" and isinstance(change.after, (int, float)):
        base = project.get(settings, keys[0]) or 0.0
        delta = float(change.after) - base
        return {k: (project.get(settings, k) or base) + delta for k in keys}
    return {k: change.after for k in keys}


def _companions(change: Change, settings: dict) -> list[Change]:
    out = []
    for key, rule in (kb.param(change.key).get("companions") or {}).items():
        current = project.get_text(settings, key)
        if current in rule["when"]:
            out.append(Change(key=key, before=current, after=rule["set"], companion=True,
                              reason=f"required for {change.key} to take effect", label=key))
    return out


def validate(changes: list[Change], defect: str, settings: dict, history: list[Change] | None = None,
             operator: bool = False) -> tuple[Validation, list[Change]]:
    """Checks the patch and returns the normalized changes (before values, real keys, companions)."""
    errors: list[str] = []
    warnings: list[str] = []
    history = history or []
    allowed = {c.key: c for c in kb.candidates(defect)}
    primary = [c for c in changes if not c.companion]

    if not primary:
        errors.append("the patch contains no changes")
    if len(primary) > LOOP.max_changes:
        errors.append(f"at most {LOOP.max_changes} parameters per iteration ({len(primary)} proposed)")
    if len({c.key for c in primary}) != len(primary):
        errors.append("the same key appears more than once")

    normalized: list[Change] = []
    for change in primary:
        key = change.key
        try:
            meta = kb.param(key)
        except KeyError:
            errors.append(f"{key}: parameter not in the knowledge base")
            continue
        cand = allowed.get(key)
        if cand is None and not operator:
            errors.append(f"{key}: not a candidate for '{defect}'")
            continue
        if not isinstance(change.after, (int, float)):
            errors.append(f"{key}: non-numeric value")
            continue
        before = project.current_value(settings, key, meta)
        if before is None:
            errors.append(f"{key}: key missing or non-numeric in the project")
            continue
        step = float(meta["step"])
        after = round(float(change.after), 3)
        delta = after - before
        lo, hi = kb.bounds(key, settings)

        if abs(delta) < EPS:
            errors.append(f"{key}: the proposed value equals the current one ({before:g})")
        if after < lo - EPS or after > hi + EPS:
            errors.append(f"{key}: {after:g} out of bounds [{lo:g}, {hi:g}] {meta['unit']}")
        if cand is not None and delta * cand.sign < 0:
            (warnings if operator else errors).append(
                f"{key}: opposite direction to the one expected for '{defect}' ({cand.direction})")
        outside = before < lo - EPS or before > hi + EPS
        if outside and abs(after - min(hi, max(lo, before))) < EPS:
            warnings.append(f"{key}: the current value {before:g} is out of bounds, brought back to {after:g}")
        elif abs(delta) > 2 * step + EPS:
            (warnings if operator else errors).append(
                f"{key}: change {delta:+g} beyond the maximum step ±{2 * step:g} {meta['unit']}")
        for past in history:
            if past.key == key and isinstance(past.after, (int, float)) and isinstance(past.before, (int, float)):
                if (past.after - past.before) * delta < 0:
                    (warnings if operator else errors).append(
                        f"{key}: oscillation, a previous iteration moved it from {past.before:g} to {past.after:g}")

        norm = change.model_copy(update={"before": before, "after": after, "label": meta["label"], "unit": meta["unit"]})
        norm.real = real_changes(norm, settings)
        normalized.append(norm)
        normalized.extend(_companions(norm, settings))

    if not errors:
        for key in {k for c in normalized for k in c.real}:
            if key not in settings:
                errors.append(f"{key}: key missing in the project")
    return Validation(ok=not errors, errors=errors, warnings=warnings), normalized


def real_map(changes: list[Change], settings: dict) -> dict[str, float | str]:
    out: dict[str, float | str] = {}
    for change in changes:
        out.update(change.real or real_changes(change, settings))
    return out
