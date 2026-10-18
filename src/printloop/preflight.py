"""Pre-flight: checks on the G-code that the patch propagated and does not exceed the limits.

Two levels of checks for each change:
1. propagation: the CONFIG_BLOCK of the new G-code carries the patched value;
2. effect on the toolpath: the measure tied to the parameter (kb.yaml, `check`) moves in the expected
   direction, by at least a fraction of the change that was set. If the feature does not exist in the
   model (e.g. bridges on a part without any) the patch is useless and the check fails.
Then the global limits on the new G-code: volumetric flow, temperatures within the material range.
"""
from __future__ import annotations

from printloop import kb, project
from printloop.gcode import GcodeStats
from printloop.models import Change, Check, Preflight

MIN_EFFECT = 0.25        # minimum fraction of the change that must show in the G-code
VOLUMETRIC_TOL = 1.05    # tolerance on the nominal volumetric flow (accelerations ignored)


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    first = text.split(",")[0].strip().strip('"').rstrip("%")
    try:
        return float(first)
    except ValueError:
        return None


def _direction(delta: float) -> str:
    return "increase" if delta > 0 else "decrease"


def _moved(before: float | None, after: float | None, expected_delta: float) -> tuple[str, str]:
    if before is None or after is None:
        return "fail", "measure not available in the G-code"
    measured = after - before
    if measured * expected_delta <= 0:
        return "fail", f"expected {_direction(expected_delta)}, measured {measured:+.3g}"
    if abs(measured) < MIN_EFFECT * abs(expected_delta):
        return "fail", f"effect too small: {measured:+.3g} out of {expected_delta:+.3g} set"
    return "pass", f"{measured:+.3g} (set {expected_delta:+.3g})"


def _propagation(change: Change, before: GcodeStats, after: GcodeStats) -> list[Check]:
    checks = []
    for key, value in change.real.items():
        found = after.config.get(key)
        if isinstance(value, str):
            ok = found is not None and found.split(",")[0].strip() == value
            checks.append(Check(check="config", key=change.key, target=key, expected=value,
                                status="pass" if ok else "fail", detail=f"G-code: {before.config.get(key)} → {found}"))
            continue
        got = _num(found)
        ok = got is not None and abs(got - float(value)) < 1e-6 + 1e-4 * abs(float(value))
        checks.append(Check(check="config", key=change.key, target=key, before=_num(before.config.get(key)),
                            after=got, expected=f"{float(value):g}",
                            status="pass" if ok else "fail",
                            detail="value written in the G-code" if ok else f"in the G-code: {found}"))
    return checks


def _effect(change: Change, before: GcodeStats, after: GcodeStats) -> Check:
    check = kb.param(change.key)["check"]
    kind = check["type"]
    features = check.get("features", [])
    target = ", ".join(features) if features else change.key
    delta = float(change.after) - float(change.before)
    expected = f"{_direction(delta)} to {float(change.after):g}"

    def feature_metric(metric: str, first_layer: bool = False) -> Check:
        fb, fa = before.feature(features, first_layer), after.feature(features, first_layer)
        if fb.length_mm == 0 and fa.length_mm == 0:
            where = "in the first layer" if first_layer else "in the model"
            return Check(check=kind, key=change.key, target=target, expected=expected, status="fail",
                         detail=f"feature '{target}' missing {where}: the change has no effect")
        if metric == "speed":
            b, a = fb.speed(), fa.speed()
            status, detail = _moved(b, a, delta)
        elif metric == "fan":
            b, a = fb.fan(), fa.fan()
            status, detail = _moved(b, a, delta)
            if status == "fail" and b is not None and b >= 99.5 and delta > 0:
                detail = "fan already at maximum during the feature: the change has no effect"
        else:  # e_per_mm: compare the ratios
            b, a = fb.e_per_mm(), fa.e_per_mm()
            ratio = float(change.after) / float(change.before)
            if b and a:
                status, detail = _moved(1.0, a / b, ratio - 1.0)
                detail = f"measured ratio {a / b:.4f}, expected {ratio:.4f}"
            else:
                status, detail = "fail", "measure not available in the G-code"
        return Check(check=kind, key=change.key, target=target, before=b, after=a, expected=expected,
                     status=status, detail=detail)

    if kind == "feature_speed":
        return feature_metric("speed")
    if kind == "first_layer_speed":
        return feature_metric("speed", first_layer=True)
    if kind == "fan_during":
        return feature_metric("fan")
    if kind == "extrusion_per_mm":
        return feature_metric("e_per_mm")
    if kind in ("hotend_setpoint", "bed_setpoint"):
        layer = int(check.get("layer", 1))
        series = "hotend" if kind == "hotend_setpoint" else "bed"
        b, a = before.setpoint(series, layer), after.setpoint(series, layer)
        want = float(change.after)
        if kind == "bed_setpoint":
            want = float(next(iter(change.real.values())))
        ok = a is not None and abs(a - want) < 0.51
        return Check(check=kind, key=change.key, target=f"layer {layer}", before=b, after=a, expected=f"{want:g} °C",
                     status="pass" if ok else "fail", detail="setpoint in the G-code" if ok else "different setpoint")
    if kind == "retraction":
        b, a = before.retraction_median(), after.retraction_median()
        ok = a is not None and abs(a - float(change.after)) < 0.051
        return Check(check=kind, key=change.key, target="retractions", before=b, after=a,
                     expected=f"{float(change.after):g} mm", status="pass" if ok else "fail",
                     detail=f"median of {len(after.retractions)} retractions")
    if kind == "feature_length":
        b, a = before.feature(features).length_mm, after.feature(features).length_mm
        status, detail = _moved(b, a, delta)
        return Check(check=kind, key=change.key, target=target, before=round(b, 1), after=round(a, 1),
                     expected=expected, status=status, detail=f"extruded length: {detail}")
    if kind == "volumetric_limit":
        b, a = before.volumetric_p99(), after.volumetric_p99()
        ok = a is not None and a <= float(change.after) * VOLUMETRIC_TOL
        return Check(check=kind, key=change.key, target="volumetric flow p99", before=b, after=a,
                     expected=f"≤ {float(change.after):g} mm³/s", status="pass" if ok else "fail",
                     detail="respected" if ok else "the G-code exceeds the new limit")
    return Check(check=kind, key=change.key, target=target, status="fail", detail=f"unknown check type: {kind}")


def _limit(check: str, target: str, before: float | None, after: float, ok: bool, expected: str, detail: str) -> Check:
    """A limit fails only if the patch makes it worse; if it was already exceeded and does not get worse, it passes."""
    if ok:
        return Check(check=check, target=target, before=before, after=after, expected=expected, detail=detail)
    if before is not None and abs(after - before) < 1e-9:
        return Check(check=check, target=target, before=before, after=after, expected=expected, status="pass",
                     detail=f"{detail}; already over the limit before the patch, unchanged")
    return Check(check=check, target=target, before=before, after=after, expected=expected, status="fail",
                 detail=f"{detail}; exceeded by the patch")


def _limits(before: GcodeStats, after: GcodeStats, settings_after: dict) -> list[Check]:
    limits = []
    vmax = project.get(settings_after, "filament_max_volumetric_speed")
    p99, p99_before = after.volumetric_p99(), before.volumetric_p99()
    if vmax is not None and p99 is not None:
        ok = p99 <= vmax * VOLUMETRIC_TOL
        chk = _limit("max_volumetric_speed", "volumetric flow p99", _r(p99_before), round(p99, 2), ok,
                     f"≤ {vmax:g} mm³/s", "nominal, accelerations excluded")
        if not ok and p99_before is not None and p99 < p99_before - 1e-6:
            chk.status, chk.detail = "pass", "still above the limit but lower than before the patch"
        limits.append(chk)
    rng = project.filament_range(settings_after)
    if rng:
        for layer in (0, 1):
            temp = after.setpoint("hotend", layer)
            if temp is None:
                continue
            ok = rng[0] - 0.5 <= temp <= rng[1] + 0.5
            limits.append(_limit("nozzle_range", f"layer {layer}", before.setpoint("hotend", layer), temp, ok,
                                 f"{rng[0]:g}–{rng[1]:g} °C", "filament range"))
    bed = after.setpoint("bed", 1)
    _, bed_max = kb.bounds("bed_temperature", settings_after)
    if bed is not None:
        limits.append(_limit("bed_max", "layer 1", before.setpoint("bed", 1), bed, bed <= bed_max + 0.5,
                             f"≤ {bed_max:g} °C", f"material {project.material(settings_after)}"))
    return limits


def grams(stats: GcodeStats, settings: dict) -> float:
    diameter = project.get(settings, "filament_diameter") or 1.75
    area_mm2 = 3.141592653589793 * (diameter / 2) ** 2
    return round(stats.filament_mm * area_mm2 / 1000.0 * project.density(settings), 2)


def ui_checks(changes: list[Change], delivered_settings: dict) -> list[Check]:
    """Every patched key must be listed as "modified against the system preset" in the delivered 3MF.

    That is the rule OrcaSlicer applies when it reopens a project: keys not listed in different_settings_to_system
    go back to the system preset value (update_non_diff_values_to_base_config).
    """
    checks = []
    for change in changes:
        for key in change.real:
            ok = project.is_marked(delivered_settings, key)
            checks.append(Check(check="slicer_ui", key=change.key, target=key, expected="declared modified",
                                status="pass" if ok else "fail",
                                detail="visible when opened in OrcaSlicer/BambuStudio" if ok else
                                "not declared in different_settings_to_system: the slicer would show the system value"))
    return checks


def run(before: GcodeStats, after: GcodeStats, changes: list[Change], settings_before: dict, settings_after: dict,
        time_before_s: float | None = None, time_after_s: float | None = None,
        delivered_settings: dict | None = None) -> Preflight:
    checks: list[Check] = []
    for change in changes:
        checks.extend(_propagation(change, before, after))
        if not change.companion:
            checks.append(_effect(change, before, after))
    if delivered_settings is not None:
        checks.extend(ui_checks(changes, delivered_settings))
    limits = _limits(before, after, settings_after)
    side = {
        "print_time_s": [_r(time_before_s), _r(time_after_s)],
        "filament_g": [grams(before, settings_before), grams(after, settings_after)],
        "layers": [before.layers, after.layers],
    }
    ok = all(c.status != "fail" for c in checks) and all(c.status != "fail" for c in limits)
    return Preflight(ok=ok, checks=checks, limits=limits, side_effects=side)


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 1)
