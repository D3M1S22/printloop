"""Test end-to-end con lo slicer reale (saltati se BambuStudio/OrcaSlicer non è installato)."""
import io

import pytest
from PIL import Image

from printloop import config, slicer, testset

pytestmark = pytest.mark.skipif(not slicer.available() or not testset.COUPON_3MF.exists(),
                                reason="slicer o coupon non disponibili")


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
    assert (loop.case_dir(case.id) / it.sliced_3mf).exists()

    # modifica dell'operatore: oltre il passo della KB, dentro i limiti -> avviso, ricalcolo, approvazione
    case = loop.decide(case.id, approved=True, reason="vado più piano", edits={"bridge_speed": 40})
    assert case.state == "awaiting_photos" and case.iterations[0].decision.edited
    assert case.iterations[0].proposal.source == "operator"

    loop.add_photos(case.id, [("front.jpg", _photo())])
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
    case = loop.decide(case.id, approved=False, reason="voglio prima calibrare il flow")
    assert case.state == "diagnosed" and case.rejected_keys == ["filament_flow_ratio"]
    case = loop.propose_case(case.id)
    assert case.state == "escalated"  # unico candidato rifiutato


def test_non_fixable_defect_escalates(runs, cases):
    from printloop import loop
    case = loop.create(cases / "C0_baseline" / "project.3mf")
    case = loop.diagnose_case(case.id, mode="operator", defect="layer_shift", severity=3)
    assert case.state == "escalated" and "meccanica" in case.message


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
    """Percorso LLM con risposte simulate: diagnosi, proposta non valida scartata, poi proposta valida."""
    from printloop import llm, loop
    calls = []

    def fake_chat_json(messages, schema, name="output", **kw):
        calls.append(name)
        if name == "diagnosis":
            assert any(part.get("type") == "image_url" for part in messages[1]["content"])
            return {"findings": [{"defect": "stringing", "severity": 3, "confidence": 0.82,
                                  "evidence": [{"photo": "a.jpg", "description": "fili tra i pilastri"}],
                                  "location": "tra i pilastri"}],
                    "primary": "stringing", "needs_more_info": False, "question_for_operator": ""}, 12.0
        # prima proposta fuori passo (scartata dal validatore), poi si passa alle regole
        return {"changes": [{"key": "retraction_length", "value": 1.9, "reason": "troppo poca retrazione"}],
                "rationale": "retrazione quasi nulla", "expected_effect": "meno fili"}, 8.0

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
        "question_for_operator": "Foto ravvicinata della superficie superiore, per favore."}, 5.0))
    case = loop.create(cases / "C4_under_extrusion" / "project.3mf")
    loop.add_photos(case.id, [("a.jpg", _photo())])
    case = loop.diagnose_case(case.id)
    assert case.state == "needs_info" and "ravvicinata" in case.message
    # l'operatore corregge a mano la diagnosi
    case = loop.diagnose_case(case.id, mode="operator", defect="under_extrusion", severity=2)
    assert case.state == "diagnosed"
