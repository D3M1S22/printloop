"""Generates the JSON fixtures for the frontend (web/fixtures/) from a real case run through the API.

Scenario: C1 (bridges at double speed). Diagnosis stated by the operator (offline), rule-based patch,
rejection with a reason, new proposal, operator edit, approval, reprint, closing; then a step back to the
reprint diagnosis and the operator confirming the reprint is good.
Second case: layer shift -> escalation (not fixable from the preset).
Usage: `PRINTLOOP_RUNS_DIR=runs/fixtures uv run python scripts/export_fixtures.py`
"""
from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from printloop import testset
from printloop.api import app
from printloop.config import ROOT

OUT = ROOT / "web" / "fixtures"


def photo(text: str) -> bytes:
    img = Image.new("RGB", (640, 480), (215, 215, 210))
    ImageDraw.Draw(img).text((20, 20), text, fill=(40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def dump(name: str, data) -> None:
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"web/fixtures/{name}.json")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = ROOT / "runs" / "fixtures_testset"
    testset.build_testset(cases, slice_cases=False)
    client = TestClient(app)

    def ok(res):
        assert res.status_code == 200, res.text
        return res.json()

    dump("health", ok(client.get("/api/health")))
    dump("taxonomy", ok(client.get("/api/taxonomy")))
    with open(cases / "C1_bridge_speed" / "project.3mf", "rb") as fh:
        case = ok(client.post("/api/cases", files={"project": ("bridge_test.3mf", fh)}, data={"name": "Bridge test"}))
    cid = case["id"]
    dump("case_created", case)
    dump("case_ready", ok(client.post(f"/api/cases/{cid}/photos", data={"note": "the bridges sag in the middle"},
                                      files=[("photos", ("front.jpg", photo("front"), "image/jpeg")),
                                             ("photos", ("macro.jpg", photo("macro"), "image/jpeg"))])))
    dump("case_diagnosed", ok(client.post(f"/api/cases/{cid}/diagnose",
                                          json={"mode": "operator", "defect": "bridge_sagging", "severity": 3})))
    dump("case_awaiting_approval", ok(client.post(f"/api/cases/{cid}/propose", json={"mode": "rules"})))
    dump("case_rejected", ok(client.post(f"/api/cases/{cid}/decision",
                                         json={"approved": False, "reason": "trying the fan first"})))
    dump("case_awaiting_approval_2", ok(client.post(f"/api/cases/{cid}/propose", json={"mode": "rules"})))
    dump("case_edited", ok(client.post(f"/api/cases/{cid}/decision",
                                       json={"approved": False, "edits": {"bridge_flow": 0.9},
                                             "reason": "slightly lower flow"})))
    dump("case_approved", ok(client.post(f"/api/cases/{cid}/decision", json={"approved": True, "reason": "ok"})))
    dump("case_iter2_ready", ok(client.post(f"/api/cases/{cid}/photos",
                                            files=[("photos", ("front.jpg", photo("reprint"), "image/jpeg"))])))
    dump("case_done", ok(client.post(f"/api/cases/{cid}/diagnose",
                                     json={"mode": "operator", "defect": "bridge_sagging", "severity": 1})))
    ok(client.post(f"/api/cases/{cid}/rewind", json={"iteration": 2, "step": "diagnosis"}))
    dump("case_confirmed", ok(client.post(f"/api/cases/{cid}/confirm", json={"note": "bridges are flat now"})))
    with open(cases / "C0_baseline" / "project.3mf", "rb") as fh:
        other = ok(client.post("/api/cases", files={"project": ("bracket.3mf", fh)}, data={"name": "Motor bracket"}))
    ok(client.post(f"/api/cases/{other['id']}/photos", files=[("photos", ("side.jpg", photo("side"), "image/jpeg"))]))
    dump("case_escalated", ok(client.post(f"/api/cases/{other['id']}/diagnose",
                                          json={"mode": "operator", "defect": "layer_shift", "severity": 3})))
    dump("cases", ok(client.get("/api/cases")))
    dump("audit", ok(client.get(f"/api/cases/{cid}/audit")))


if __name__ == "__main__":
    main()
