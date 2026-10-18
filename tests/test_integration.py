"""End-to-end tests with the real slicer (skipped if BambuStudio/OrcaSlicer is not installed)."""
import io

import pytest
from PIL import Image

from printloop import config, slicer, testset

pytestmark = pytest.mark.skipif(not slicer.available() or not testset.COUPON_3MF.exists(),
                                reason="slicer or coupon not available")


@pytest.fixture()
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOOP", config.LoopConfig(runs_dir=tmp_path / "runs"))
    from printloop import loop
    monkeypatch.setattr(loop, "LOOP", config.LOOP)
    return tmp_path


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    out = tmp_path_factory.mktemp("testset")
    testset.build_testset(out, slice_cases=False)
    return out


def _photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (90, 90, 90)).save(buf, "JPEG")
    return buf.getvalue()


def test_full_loop_bridge(runs, cases):
    from printloop import loop
    case = loop.create(cases / "C1_bridge_speed" / "project.3mf")
    assert case.state == "awaiting_photos" and case.baseline["print_time_s"] > 0
    loop.add_photos(case.id, [("front.jpg", _photo())])
    case = loop.diagnose_case(case.id, mode="operator", defect="bridge_sagging", severity=3)
    case = loop.propose_case(case.id, mode="rules")
    it = case.current
    assert case.state == "awaiting_approval" and it.preflight.ok
    assert it.proposal.changes[0].key == "bridge_speed" and it.proposal.changes[0].after == 80
    delivered = loop.case_dir(case.id) / it.sliced_3mf
    assert delivered.exists()
    # the delivered 3MF declares the patch as modified (otherwise OrcaSlicer resets it to the system value)
    from printloop import project
    assert project.is_marked(project.read_settings(delivered), "bridge_speed")
    assert any(c.check == "slicer_ui" and c.status == "pass" for c in it.preflight.checks)
    # ...and the G-code inside the 3MF is intact
    import hashlib
    import zipfile
    with zipfile.ZipFile(delivered) as zf:
        gcode_bytes = zf.read("Metadata/plate_1.gcode")
        assert hashlib.md5(gcode_bytes).hexdigest().upper() == zf.read("Metadata/plate_1.gcode.md5").decode().strip().upper()

    # operator edit: beyond the KB step, within bounds -> warning, recompute, approval
    case = loop.decide(case.id, approved=True, reason="going slower", edits={"bridge_speed": 40})
    assert case.state == "awaiting_photos" and case.iterations[0].decision.edited
    assert case.iterations[0].proposal.source == "operator"

    loop.add_photos(case.id, [("front.jpg", _photo())])
    # the approved patch stays declared in the project of the next iteration too
    from printloop import project as prj
    assert prj.is_marked(prj.read_settings(loop.case_dir(case.id) / case.current.project), "bridge_speed")
    case = loop.diagnose_case(case.id, mode="operator", defect="bridge_sagging", severity=1)
    assert case.state == "done" and case.outcome == "fixed"
    events = [row["event"] for row in loop.audit_log(case.id)]
    assert events[0] == "case_created" and "proposal_edited" in events and events[-1] == "done"


def test_reject_then_escalate_without_candidates(runs, cases):
    from printloop import loop
    case = loop.create(cases / "C3_over_extrusion" / "project.3mf")
    case = loop.diagnose_case(case.id, mode="operator", defect="over_extrusion", severity=2)
    case = loop.propose_case(case.id)
    assert case.current.proposal.changes[0].key == "filament_flow_ratio"
    case = loop.decide(case.id, approved=False, reason="calibrating the flow first")
    assert case.state == "diagnosed" and case.rejected_keys == ["filament_flow_ratio"]
    case = loop.propose_case(case.id)
    assert case.state == "escalated"  # the only candidate was rejected


def test_non_fixable_defect_escalates(runs, cases):
    from printloop import loop
    case = loop.create(cases / "C0_baseline" / "project.3mf")
    case = loop.diagnose_case(case.id, mode="operator", defect="layer_shift", severity=3)
    assert case.state == "escalated" and "mechanical" in case.message


def test_api_flow(runs, cases):
    from fastapi.testclient import TestClient

    from printloop.api import app
    client = TestClient(app)
    assert client.get("/api/health").json()["slicer"]["available"]
    with open(cases / "C6_stringing_retraction" / "project.3mf", "rb") as fh:
        res = client.post("/api/cases", files={"project": ("c6.3mf", fh, "application/octet-stream")},
                          data={"name": "api"})
    assert res.status_code == 200, res.text
    case_id = res.json()["id"]
    res = client.post(f"/api/cases/{case_id}/photos", files=[("photos", ("a.jpg", _photo(), "image/jpeg"))])
    assert res.json()["state"] == "ready"
    res = client.post(f"/api/cases/{case_id}/diagnose", json={"mode": "operator", "defect": "stringing", "severity": 2})
    assert res.json()["state"] == "diagnosed"
    res = client.post(f"/api/cases/{case_id}/propose", json={"mode": "rules"})
    body = res.json()
    assert body["state"] == "awaiting_approval"
    assert body["iterations"][0]["proposal"]["changes"][0]["key"] == "retraction_length"
    options = {o["key"]: o for o in body["edit_options"]}
    assert options["retraction_length"]["proposed"] == 0.2 and options["retraction_length"]["current"] == 0.1
    assert options["nozzle_temperature"]["min"] == 190 and options["nozzle_temperature"]["max"] == 240
    assert client.get(body["iterations"][0]["print_file_url"]).status_code == 200
    assert client.post(f"/api/cases/{case_id}/decision", json={"approved": False}).status_code == 409
    res = client.post(f"/api/cases/{case_id}/decision", json={"approved": True, "reason": "ok"})
    assert res.json()["state"] == "awaiting_photos" and res.json()["latest_print_file_url"]
    assert client.get(f"/api/cases/{case_id}/files/../../etc/passwd").status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404


def test_llm_path_with_fake_model(runs, cases, monkeypatch):
    """LLM path with faked replies: diagnosis, invalid proposal discarded, then a valid proposal."""
    from printloop import llm, loop
    calls = []

    def fake_chat_json(messages, schema, name="output", **kw):
        calls.append(name)
        if name == "diagnosis":
            assert any(part.get("type") == "image_url" for part in messages[1]["content"])
            return {"findings": [{"defect": "stringing", "severity": 3, "confidence": 0.82,
                                  "evidence": [{"photo": "a.jpg", "description": "strings between the pillars"}],
                                  "location": "between the pillars"}],
                    "primary": "stringing", "needs_more_info": False, "question_for_operator": ""}, 12.0
        # first proposal beyond the step (discarded by the validator), then the rules take over
        return {"changes": [{"key": "retraction_length", "value": 1.9, "reason": "too little retraction"}],
                "rationale": "almost no retraction", "expected_effect": "fewer strings"}, 8.0

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    case = loop.create(cases / "C6_stringing_retraction" / "project.3mf")
    loop.add_photos(case.id, [("a.jpg", _photo())])
    case = loop.diagnose_case(case.id)
    assert case.current.diagnosis.source == "llm" and case.state == "diagnosed"
    case = loop.propose_case(case.id)
    proposal = case.current.proposal
    assert calls == ["diagnosis", "patch"]
    assert proposal.rejected_attempts[0].source == "llm" and proposal.rejected_attempts[0].stage == "validation"
    assert proposal.source == "rules" and proposal.changes[0].key == "retraction_length"
    assert case.state == "awaiting_approval"


def test_low_confidence_asks_for_more_info(runs, cases, monkeypatch):
    from printloop import llm, loop
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: ({
        "findings": [{"defect": "under_extrusion", "severity": 2, "confidence": 0.3, "evidence": [], "location": ""}],
        "primary": "under_extrusion", "needs_more_info": True,
        "question_for_operator": "Please take a close-up photo of the top surface."}, 5.0))
    case = loop.create(cases / "C4_under_extrusion" / "project.3mf")
    loop.add_photos(case.id, [("a.jpg", _photo())])
    case = loop.diagnose_case(case.id)
    assert case.state == "needs_info" and "close-up" in case.message
    # the operator corrects the diagnosis manually
    case = loop.diagnose_case(case.id, mode="operator", defect="under_extrusion", severity=2)
    assert case.state == "diagnosed"


def _approved_case(loop, cases, photos_iter2: bool = False):
    """C1 case with the first patch approved, waiting for (or holding) the photos of the reprint."""
    case = loop.create(cases / "C1_bridge_speed" / "project.3mf")
    loop.add_photos(case.id, [("front.jpg", _photo())])
    loop.diagnose_case(case.id, mode="operator", defect="bridge_sagging", severity=3)
    loop.propose_case(case.id, mode="rules")
    case = loop.decide(case.id, approved=True, reason="ok")
    if photos_iter2:
        case = loop.add_photos(case.id, [("reprint.jpg", _photo())])
    return case


def test_confirm_success_closes_the_reprint(runs, cases):
    from printloop import loop
    first = loop.create(cases / "C1_bridge_speed" / "project.3mf")
    with pytest.raises(loop.CaseError):
        loop.confirm_success(first.id)  # nothing approved yet: there is no reprint to confirm
    case = _approved_case(loop, cases)
    assert loop.can_confirm(case)
    case = loop.confirm_success(case.id, note="bridges are flat now")
    assert case.state == "done" and case.outcome == "fixed" and case.current.confirmed.note
    assert loop.audit_log(case.id)[-1]["event"] == "confirmed_success"
    # undoing the confirmation reopens the reprint step
    last = loop.rewind_targets(case)[-1]
    assert (last["iteration"], last["step"]) == (2, "photos") and last["discards"] == ["the success confirmation"]
    case = loop.rewind(case.id, 2, "photos")
    assert case.state == "awaiting_photos" and case.outcome is None and case.current.confirmed is None


def test_rewind_to_previous_iteration_archives_later_files(runs, cases):
    from printloop import loop
    case = _approved_case(loop, cases, photos_iter2=True)
    root = loop.case_dir(case.id)
    assert (root / "iter_2" / "photos" / "reprint.jpg").exists()
    last = loop.rewind_targets(case)[-1]
    assert (last["iteration"], last["step"]) == (2, "photos")
    assert last["discards"] == ["1 photo of iteration 2"]
    assert loop.rewind_targets(case)[-2]["discards"] == ["the approval of iteration 1", "iteration 2 (1 photo)"]
    case = loop.rewind(case.id, 1, "approval")
    assert case.state == "awaiting_approval" and len(case.iterations) == 1 and case.current.decision is None
    assert not (root / "iter_2").exists()
    archives = list((root / "discarded").glob("*_rewind_iter1_approval"))
    assert len(archives) == 1
    assert (archives[0] / "iter_2" / "photos" / "reprint.jpg").exists() and (archives[0] / "case.json").exists()
    # the patch files of iteration 1 are still there and the approval can be repeated
    assert (root / case.current.sliced_3mf).exists()
    case = loop.decide(case.id, approved=True, reason="ok again")
    assert case.state == "awaiting_photos" and case.current.n == 2


def test_rewind_within_an_iteration(runs, cases):
    from printloop import loop
    case = loop.create(cases / "C3_over_extrusion" / "project.3mf")
    loop.add_photos(case.id, [("front.jpg", _photo())])
    loop.diagnose_case(case.id, mode="operator", defect="over_extrusion", severity=2)
    case = loop.propose_case(case.id, mode="rules")
    root = loop.case_dir(case.id)
    assert (root / "iter_1" / "attempt_1").exists()
    # one step back from the approval discards the patch without rejecting it
    case = loop.rewind(case.id, 1, "patch")
    assert case.state == "diagnosed" and case.current.proposal is None and case.rejected_keys == []
    assert not (root / "iter_1" / "attempt_1").exists()
    case = loop.propose_case(case.id, mode="rules")
    case = loop.decide(case.id, approved=False, reason="calibrating the flow first")
    assert case.rejected_keys == ["filament_flow_ratio"]
    # going back to the diagnosis drops the rejections made against it, photos stay
    case = loop.rewind(case.id, 1, "diagnosis")
    assert case.state == "ready" and case.current.diagnosis is None and case.rejected_keys == []
    assert case.current.photos and (root / case.current.photos[0]).exists()
    case = loop.rewind(case.id, 1, "photos")
    assert case.state == "awaiting_photos" and case.current.photos == []
    assert loop.rewind_targets(case) == []
    with pytest.raises(loop.CaseError):
        loop.rewind(case.id, 1, "approval")
    events = [row["event"] for row in loop.audit_log(case.id)]
    assert events.count("rewound") == 3


def test_api_delete_confirm_rewind(runs, cases):
    from fastapi.testclient import TestClient

    from printloop import loop
    from printloop.api import app
    client = TestClient(app)
    case = _approved_case(loop, cases)
    summary = next(c for c in client.get("/api/cases").json() if c["id"] == case.id)
    assert "confirm_success" in summary["allowed_actions"] and "rewind" in summary["allowed_actions"]
    body = client.get(f"/api/cases/{case.id}").json()
    assert body["rewind_targets"][-1] == {"iteration": 1, "step": "approval",
                                          "discards": ["the approval of iteration 1"]}
    res = client.post(f"/api/cases/{case.id}/rewind", json={"iteration": 1, "step": "approval"})
    assert res.status_code == 200 and res.json()["state"] == "awaiting_approval"
    assert client.post(f"/api/cases/{case.id}/confirm", json={}).status_code == 409
    assert client.post(f"/api/cases/{case.id}/rewind", json={"iteration": 1, "step": "photos", "x": 1}).status_code == 200
    assert client.post(f"/api/cases/{case.id}/rewind", json={"iteration": 1, "step": "patch"}).status_code == 409
    assert client.delete(f"/api/cases/{case.id}").json() == {"deleted": case.id}
    assert not loop.case_dir(case.id).exists()
    assert client.get(f"/api/cases/{case.id}").status_code == 404
    assert client.delete(f"/api/cases/{case.id}").status_code == 404


def _two_models(monkeypatch, detector_answer, model_answer):
    """Fakes both models: the E4B detector (per photo) and the 26B (diagnosis)."""
    from printloop import detector, llm
    seen = {"hint": None}
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "vision_available", lambda: True)

    def fake_detect(image):
        if isinstance(detector_answer, Exception):
            return detector.Detection(error=str(detector_answer))
        return detector.Detection(defects=detector_answer, primary=(detector_answer or ["none"])[0], model="e4b",
                                  latency_ms=5.0)

    def fake_chat(messages, schema, name="output", **kw):
        texts = [p["text"] for p in messages[1]["content"] if p.get("type") == "text"]
        seen["hint"] = next((t for t in texts if t.startswith("A defect classifier")), None)
        defect, severity = model_answer
        findings = [] if defect == "none" else [{"defect": defect, "severity": severity, "confidence": 0.9,
                                                 "evidence": [], "location": ""}]
        return {"findings": findings, "primary": defect, "needs_more_info": False, "question_for_operator": ""}, 9.0

    monkeypatch.setattr(detector, "detect", fake_detect)
    monkeypatch.setattr(llm, "chat_json", fake_chat)
    return seen


@pytest.mark.parametrize("detected,model,state,agreement", [
    (["stringing"], ("stringing", 2), "diagnosed", "agree"),
    (["stringing"], ("under_extrusion", 2), "needs_info", "disagree"),
    (["stringing"], ("none", 0), "needs_info", "disagree"),
    ([], ("stringing", 3), "needs_info", "disagree"),
    ([], ("none", 0), "done", "agree"),
    (RuntimeError("down"), ("stringing", 2), "diagnosed", "unavailable"),
])
def test_two_model_diagnosis(runs, cases, monkeypatch, detected, model, state, agreement):
    from printloop import loop
    seen = _two_models(monkeypatch, detected, model)
    case = loop.create(cases / "C6_stringing_retraction" / "project.3mf")
    case = loop.add_photos(case.id, [("front.jpg", _photo()), ("side.jpg", _photo())])
    assert len(case.current.detections) == 2
    case = loop.diagnose_case(case.id, mode="llm")
    assert case.state == state and case.current.diagnosis.detector.agreement == agreement
    if isinstance(detected, list):
        assert "front.jpg: " in seen["hint"]
    else:
        assert seen["hint"] is None
    if state == "needs_info":
        assert "detector" in case.message
        # the operator settles it; the case goes on
        case = loop.diagnose_case(case.id, mode="operator", defect="stringing", severity=2)
        assert case.state == "diagnosed"


def test_detections_follow_the_photos(runs, cases, monkeypatch):
    from printloop import loop
    _two_models(monkeypatch, ["blobs"], ("blobs", 2))
    case = loop.create(cases / "C6_stringing_retraction" / "project.3mf")
    case = loop.add_photos(case.id, [("a.jpg", _photo())])
    assert [d.photo.split("/")[-1] for d in case.current.detections] == ["a.jpg"]
    case = loop.add_photos(case.id, [("b.jpg", _photo())])        # replace: labels of the old photo go away
    assert [d.photo.split("/")[-1] for d in case.current.detections] == ["b.jpg"]
    case = loop.diagnose_case(case.id, mode="llm")
    assert case.state == "escalated" and "Zits" in case.message   # blobs: no verifiable patch in the KB
    case = loop.rewind(case.id, 1, "photos")
    assert case.current.detections == []
    events = [row["event"] for row in loop.audit_log(case.id)]
    assert events.count("detected") == 2
