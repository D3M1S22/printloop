"""Tests of parser, settings, validator, proposal and pre-flight: they run without slicer or LLM."""
import pytest

from printloop import diagnose, gcode, preflight, project, propose, validate
from printloop.models import Change, Diagnosis, Finding

GCODE = """; total estimated time: 1m 0s
; bridge_speed = 30
; filament_diameter = 1.75
M140 S55
M104 S220
G90
M83
; CHANGE_LAYER
; FEATURE: Outer wall
M106 S255
G1 X0 Y0 F6000
G1 X10 Y0 E0.5 F6000
G1 X10 Y10 E0.5
; WIPE_START
G1 X12 Y10 E-0.6
; WIPE_END
G1 E-0.2 F1800
G1 X20 Y20 F30000
G1 E0.8 F1800
; FEATURE: Bridge
G1 X30 Y20 E0.8 F1800
G3 X40 Y20 I5 J0 E0.6
; CHANGE_LAYER
M104 S215
M106 S127.5
; FEATURE: Bridge
G1 X50 Y20 E0.8 F1800
; MACHINE_END_GCODE_START
G1 X0 Y0 E5 F3000
M104 S0
"""


def settings_fixture(**over):
    base = {"bridge_speed": ["50", "50"], "filament_flow_ratio": ["0.98"], "nozzle_temperature": ["220"],
            "nozzle_temperature_range_low": ["190"], "nozzle_temperature_range_high": ["240"],
            "overhang_fan_speed": ["100"], "bridge_flow": "1", "retraction_length": ["0.8"],
            "filament_retraction_length": ["nil"], "curr_bed_type": "Textured PEI Plate",
            "textured_plate_temp": ["55"], "textured_plate_temp_initial_layer": ["60"], "filament_type": ["PLA"],
            "brim_type": "auto_brim", "brim_width": "5", "overhang_fan_threshold": ["50%"],
            "different_settings_to_system": ["", "", ""]}
    base.update(over)
    return base


def diag(defect, severity=2):
    return Diagnosis(findings=[Finding(defect=defect, severity=severity, confidence=0.9)], primary=defect,
                     source="operator")


# --- gcode ---------------------------------------------------------------------------------------------

def test_gcode_features_speed_extrusion_and_fan():
    st = gcode.parse_text(GCODE)
    wall = st.features["Outer wall"]
    assert wall.length_mm == pytest.approx(20.0)
    assert wall.speed() == pytest.approx(100.0)
    assert wall.e_per_mm() == pytest.approx(0.05)
    assert wall.fan() == pytest.approx(100.0)
    bridge = st.features["Bridge"]
    assert bridge.speed() == pytest.approx(30.0)
    # half-turn G3 arc with radius 5: length pi*5
    assert bridge.length_mm == pytest.approx(10 + 3.14159265 * 5 + 10, rel=1e-6)
    assert st.layers == 2
    assert st.first_layer["Bridge"].length_mm == pytest.approx(10 + 3.14159265 * 5, rel=1e-6)


def test_gcode_retraction_sums_wipe_and_ignores_end_gcode():
    st = gcode.parse_text(GCODE)
    assert st.retractions == [pytest.approx(0.8)]
    # extrusion after MACHINE_END_GCODE_START does not count
    assert st.filament_mm == pytest.approx(0.5 + 0.5 + 0.8 + 0.6 + 0.8)


def test_gcode_setpoints_and_config():
    st = gcode.parse_text(GCODE)
    assert st.setpoint("hotend", 0) == 220
    assert st.setpoint("hotend", 1) == 215
    assert st.setpoint("bed", 1) == 55
    assert st.config["bridge_speed"] == "30"
    assert st.features["Bridge"].fan() == pytest.approx(100.0 * (10 + 3.14159265 * 5) / (20 + 3.14159265 * 5), abs=50)


def test_gcode_absolute_extrusion():
    st = gcode.parse_text("M82\n; CHANGE_LAYER\n; FEATURE: Inner wall\nG92 E0\nG1 X10 Y0 E1 F600\nG1 X20 Y0 E2\n")
    assert st.features["Inner wall"].e_mm == pytest.approx(2.0)
    assert st.features["Inner wall"].speed() == pytest.approx(10.0)


# --- settings -------------------------------------------------------------------------------------------

def test_project_format_preserved():
    s = settings_fixture()
    patched = project.apply_changes(s, {"bridge_speed": 30, "bridge_flow": 0.95, "overhang_fan_threshold": 25})
    assert patched["bridge_speed"] == ["30", "30"]
    assert patched["bridge_flow"] == "0.95"
    assert patched["overhang_fan_threshold"] == ["25%"]
    assert project.get(patched, "overhang_fan_threshold") == 25


def test_project_aliases_and_overrides():
    s = settings_fixture()
    assert project.resolve_keys(s, "bed_temperature", {"alias": "bed_temperature"}) == [
        "textured_plate_temp", "textured_plate_temp_initial_layer"]
    meta = {"filament_override": "filament_retraction_length"}
    assert project.resolve_keys(s, "retraction_length", meta) == ["retraction_length"]
    s2 = settings_fixture(filament_retraction_length=["1.2"])
    assert project.resolve_keys(s2, "retraction_length", meta) == ["filament_retraction_length"]
    assert project.current_value(s2, "retraction_length", meta) == 1.2


# --- validator ------------------------------------------------------------------------------------------

def test_validator_accepts_kb_step():
    check, changes = validate.validate([Change(key="bridge_speed", after=30)], "bridge_sagging", settings_fixture())
    assert check.ok, check.errors
    assert changes[0].before == 50 and changes[0].real == {"bridge_speed": 30}


@pytest.mark.parametrize("change,defect,fragment", [
    (Change(key="bridge_speed", after=70), "bridge_sagging", "direction"),
    (Change(key="bridge_speed", after=5), "bridge_sagging", "out of bounds"),
    (Change(key="bridge_speed", after=-1), "bridge_sagging", "out of bounds"),
    (Change(key="nozzle_temperature", after=250), "stringing", "out of bounds"),
    (Change(key="filament_flow_ratio", after=0.9), "bridge_sagging", "not a candidate"),
    (Change(key="layer_height", after=0.1), "bridge_sagging", "not in the knowledge base"),
    (Change(key="bridge_speed", after=50), "bridge_sagging", "equals"),
])
def test_validator_rejects(change, defect, fragment):
    check, _ = validate.validate([change], defect, settings_fixture())
    assert not check.ok
    assert any(fragment in e for e in check.errors), check.errors


def test_validator_max_changes_and_oscillation():
    many = [Change(key="bridge_speed", after=30), Change(key="bridge_flow", after=0.95),
            Change(key="overhang_fan_speed", after=80)]
    check, _ = validate.validate(many, "bridge_sagging", settings_fixture())
    assert any("at most" in e for e in check.errors)
    history = [Change(key="nozzle_temperature", before=225, after=220)]
    check, _ = validate.validate([Change(key="nozzle_temperature", after=225)], "under_extrusion",
                                 settings_fixture(), history)
    assert any("oscillation" in e for e in check.errors)


def test_validator_operator_overrides_step_not_bounds():
    s = settings_fixture()
    check, _ = validate.validate([Change(key="filament_flow_ratio", after=0.85)], "over_extrusion", s, operator=True)
    assert check.ok and check.warnings
    check, _ = validate.validate([Change(key="filament_flow_ratio", after=0.85)], "over_extrusion", s)
    assert not check.ok
    check, _ = validate.validate([Change(key="bridge_speed", after=5)], "bridge_sagging", s, operator=True)
    assert not check.ok


def test_validator_bed_alias_and_material_cap():
    s = settings_fixture()
    check, changes = validate.validate([Change(key="bed_temperature", after=60)], "warping", s)
    assert check.ok, check.errors
    assert changes[0].real == {"textured_plate_temp": 60, "textured_plate_temp_initial_layer": 65}
    check, _ = validate.validate([Change(key="bed_temperature", after=70)], "warping", s, operator=True)
    assert not check.ok  # PLA: 65 °C maximum


def test_validator_adds_brim_companion():
    check, changes = validate.validate([Change(key="brim_width", after=9)], "warping", settings_fixture())
    assert check.ok, check.errors
    assert [c.key for c in changes] == ["brim_width", "brim_type"]
    assert changes[1].after == "outer_only" and changes[1].companion


# --- rule-based proposal ------------------------------------------------------------------------------

def test_rules_first_candidate_skips_values_at_bound():
    p = propose.propose_rules(diag("bridge_sagging"), settings_fixture(), [], set())
    assert p.changes[0].key == "bridge_speed" and p.changes[0].after == 30
    s = settings_fixture(bridge_speed=["10"])
    p = propose.propose_rules(diag("bridge_sagging"), s, [], set())
    assert p.changes[0].key == "bridge_flow"  # fan already at 100%, speed at its minimum


def test_rules_prefers_user_modified_and_extreme_values():
    s = settings_fixture(different_settings_to_system=["", "nozzle_temperature", ""])
    assert propose.propose_rules(diag("stringing"), s, [], set()).changes[0].key == "nozzle_temperature"
    s = settings_fixture(nozzle_temperature=["240"])
    assert propose.propose_rules(diag("stringing"), s, [], set()).changes[0].key == "nozzle_temperature"
    assert propose.propose_rules(diag("stringing"), settings_fixture(), [], set()).changes[0].key == "retraction_length"


def test_rules_loop_follows_severity():
    s = settings_fixture(bridge_speed=["30"])
    step = propose.PastStep("bridge_sagging", 3, [Change(key="bridge_speed", before=50, after=30)])
    improved = propose.propose_rules(diag("bridge_sagging", 2), s, [step], set())
    assert improved.changes[0].key == "bridge_speed"
    stuck = propose.propose_rules(diag("bridge_sagging", 3), s, [step], set())
    assert stuck.changes[0].key != "bridge_speed"


def test_rules_none_when_no_candidates():
    assert propose.propose_rules(diag("layer_shift"), settings_fixture(), [], set()) is None


# --- pre-flight -----------------------------------------------------------------------------------------

def _two_stats(speed_before: int, speed_after: int):
    tpl = "; bridge_speed = {v}\n; CHANGE_LAYER\n; FEATURE: Bridge\nG1 X0 Y0 F600\nG1 X10 Y0 E0.4 F{f}\n"
    return (gcode.parse_text(tpl.format(v=speed_before, f=speed_before * 60)),
            gcode.parse_text(tpl.format(v=speed_after, f=speed_after * 60)))


def test_preflight_pass_and_fail():
    s = settings_fixture()
    _, changes = validate.validate([Change(key="bridge_speed", after=30)], "bridge_sagging", s)
    before, after = _two_stats(50, 30)
    rep = preflight.run(before, after, changes, s, project.apply_changes(s, {"bridge_speed": 30}))
    assert rep.ok, rep.checks
    before, after = _two_stats(50, 50)  # the patch did not propagate
    rep = preflight.run(before, after, changes, s, s)
    assert not rep.ok
    assert {c.check for c in rep.checks if c.status == "fail"} == {"config", "feature_speed"}


def test_preflight_missing_feature_fails():
    s = settings_fixture()
    _, changes = validate.validate([Change(key="bridge_speed", after=30)], "bridge_sagging", s)
    empty = gcode.parse_text("; bridge_speed = 30\n; CHANGE_LAYER\n; FEATURE: Outer wall\nG1 X10 Y0 E0.4 F600\n")
    rep = preflight.run(empty, empty, changes, s, s)
    assert not rep.ok
    assert any("missing" in c.detail for c in rep.checks)


# --- diagnosis ------------------------------------------------------------------------------------------

def test_sanitize_llm_output():
    raw = {"findings": [{"defect": "stringing", "severity": 5, "confidence": 1.4, "evidence": [], "location": ""},
                        {"defect": "made_up", "severity": 2, "confidence": 0.5, "evidence": [], "location": ""}],
           "primary": "warping", "needs_more_info": False, "question_for_operator": ""}
    out = diagnose.sanitize(raw)
    assert [f["defect"] for f in out["findings"]] == ["stringing"]
    assert out["findings"][0]["severity"] == 3 and out["findings"][0]["confidence"] == 1.0
    assert out["primary"] == "stringing"


def test_operator_diagnosis():
    d = diagnose.diagnose_operator("none", 3)
    assert d.primary == "none" and d.severity == 0 and d.source == "operator"
    with pytest.raises(ValueError):
        diagnose.diagnose_operator("nope", 1)


# --- slicer choice --------------------------------------------------------------------------------------

def _fake_3mf(path, orca: bool):
    import zipfile
    meta = '<metadata name="OrcaSlicer">2.4.2</metadata>' if orca else ""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("3D/3dmodel.model", f'<model><metadata name="Application">BambuStudio-02.06.00.51</metadata>{meta}</model>')
    return path


def test_slicer_follows_project_origin(tmp_path, monkeypatch):
    from printloop import slicer
    monkeypatch.delenv("SLICER_BIN", raising=False)
    orca_project, bambu_project = _fake_3mf(tmp_path / "o.3mf", True), _fake_3mf(tmp_path / "b.3mf", False)
    assert slicer.project_origin(orca_project) == "orca" and slicer.project_origin(bambu_project) == "bambu"
    monkeypatch.setattr(slicer, "slicer_bins", lambda: {"orca": "/x/orca", "bambu": "/x/bambu"})
    assert slicer.choose(orca_project) == ("/x/orca", []) and slicer.choose(bambu_project) == ("/x/bambu", [])
    # Orca not installed: fall back to BambuStudio and say so
    monkeypatch.setattr(slicer, "slicer_bins", lambda: {"bambu": "/x/bambu"})
    binary, notes = slicer.choose(orca_project)
    assert binary == "/x/bambu" and "OrcaSlicer" in notes[0]


# --- different_settings_to_system (reopening in the slicer) ----------------------------------------------

def test_mark_different_sections_and_union():
    s = settings_fixture(filament_settings_id=["Bambu ASA"], different_settings_to_system=["wall_loops", "", ""])
    out, unknown = project.mark_different(s, ["bridge_speed", "overhang_fan_speed", "retraction_length", "zzz"])
    assert out["different_settings_to_system"] == ["bridge_speed;wall_loops", "overhang_fan_speed", "retraction_length"]
    assert unknown == ["zzz"]
    again, _ = project.mark_different(out, ["overhang_fan_speed"])  # no duplicates
    assert again["different_settings_to_system"][1] == "overhang_fan_speed"
    assert project.is_marked(again, "overhang_fan_speed") and not project.is_marked(s, "overhang_fan_speed")


def test_mark_different_missing_list_and_two_filaments():
    s = settings_fixture(filament_colour=["#000", "#fff"])
    s.pop("different_settings_to_system")
    out, _ = project.mark_different(s, ["filament_flow_ratio", "retraction_length"])
    assert out["different_settings_to_system"] == ["", "filament_flow_ratio", "filament_flow_ratio", "retraction_length"]


def test_every_kb_key_has_a_section():
    from printloop import kb
    keys = set()
    for key, meta in kb.load()["params"].items():
        keys.add(key)
        keys.update(meta.get("companions", {}).keys())
        if meta.get("filament_override"):
            keys.add(meta["filament_override"])
    keys.discard("bed_temperature")  # alias: the real keys are the plate ones
    keys.update(project._PLATE_KEYS)
    assert {k for k in keys if project.section_of(k) is None} == set()
