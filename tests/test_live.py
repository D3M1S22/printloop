"""Mode 1: temporal filter, frame sources, monitor and API, with a faked detector (no network, no printer)."""
import io
import struct
import time

import pytest
from PIL import Image

from printloop import config, detector, llm
from printloop.live import monitor as live
from printloop.live import policy, sources

CFG = config.Mode1Config(pause_k=3, pause_n=4, alert_k=4, alert_n=6, clear_n=6)


def feed(p, answers, layer=None, start=0):
    changed = []
    for i, defects in enumerate(answers, start):
        changed += p.update(f"{i:016x}", defects, f"t{i}", layer)
    return changed


# --- policy ---------------------------------------------------------------------------------------------------

def test_one_frame_never_alerts_and_pause_needs_3_of_4():
    p = policy.Policy(CFG)
    assert feed(p, [["spaghetti"], [], [], ["spaghetti"], [], []]) == []
    p = policy.Policy(CFG)
    raised = feed(p, [["spaghetti"], [], ["spaghetti"], ["spaghetti"]])
    assert [(a.defect, a.level) for a in raised] == [("spaghetti", "pause_proposed")]
    assert raised[0].frames == [f"{i:016x}" for i in (0, 2, 3)]


def test_warning_needs_4_of_6_and_clears_after_6_misses():
    p = policy.Policy(CFG)
    assert feed(p, [["stringing"]] * 3) == []
    raised = feed(p, [["stringing"]])
    assert raised[0].level == "warning" and raised[0].defect == "stringing"
    assert p.active["stringing"].cleared_at is None
    cleared = []
    for i in range(6):
        cleared += p.update(f"c{i:015x}", [], f"c{i}")
    assert cleared and cleared[0].cleared_at == "c5" and "stringing" not in p.active
    # it can come back as a new alert
    assert feed(p, [["stringing"]] * 4)[0].id != raised[0].id


def test_log_only_classes_and_layer_gating():
    p = policy.Policy(CFG)
    assert feed(p, [["bridge_sagging", "overhang_curling"]] * 10) == []
    p = policy.Policy(CFG)
    assert feed(p, [["stringing"]] * 6, layer=1) == []          # nothing tall enough yet
    assert feed(p, [["first_layer"]] * 6, layer=10) == []       # first layer is long gone
    assert feed(p, [["first_layer"]] * 4, layer=1)[0].defect == "first_layer"


def test_dismiss_and_evidence():
    p = policy.Policy(CFG)
    alert = feed(p, [["warping"]] * 3)[0]
    feed(p, [["warping"]] * 5, start=3)
    assert len(p.alerts[0].frames) == policy.MAX_EVIDENCE
    p.dismiss(alert.id, "it is the brim")
    assert p.alerts[0].dismissed and p.alerts[0].dismiss_reason == "it is the brim"
    assert p.evidence()[0] == f"{7:016x}"


# --- sources --------------------------------------------------------------------------------------------------

def _jpeg(color=(100, 100, 100), size=(64, 48), fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def test_replay_source_order_and_png(tmp_path):
    (tmp_path / "002.jpg").write_bytes(_jpeg((1, 1, 1)))
    (tmp_path / "001.png").write_bytes(_jpeg((2, 2, 2), fmt="PNG"))
    (tmp_path / "notes.txt").write_text("x")
    src = sources.ReplaySource(tmp_path)
    first, second = src.latest(), src.latest()
    assert (first.name, second.name) == ("001.png", "002.jpg") and first.jpeg.startswith(b"\xff\xd8")
    assert src.latest() is None and src.exhausted
    with pytest.raises(ValueError):
        sources.ReplaySource(tmp_path / "missing")


class FakeSocket:
    def __init__(self, data: bytes, chunk: int = 7):
        self.data, self.chunk = data, chunk

    def recv(self, n):
        out, self.data = self.data[:min(n, self.chunk)], self.data[min(n, self.chunk):]
        return out


def test_p1s_protocol():
    auth = sources.p1s_auth_packet("12345678")
    assert len(auth) == 80 and struct.unpack_from("<II", auth) == (0x40, 0x3000) and auth[16:20] == b"bblp"
    jpeg = _jpeg()
    stream = struct.pack("<IIII", len(jpeg), 0, 1, 0) + jpeg
    assert sources.p1s_read_frame(FakeSocket(stream)) == jpeg
    with pytest.raises(ValueError):
        sources.p1s_read_frame(FakeSocket(struct.pack("<IIII", 4, 0, 0, 0) + b"nope"))
    with pytest.raises(ValueError):
        sources.P1SCameraSource("", "")


# --- monitor and API ------------------------------------------------------------------------------------------

@pytest.fixture()
def replay(tmp_path, monkeypatch):
    """10 frames: 3 clean, then spaghetti; the fake detector reads the answer from the frame colour."""
    monkeypatch.setattr(config, "LOOP", config.LoopConfig(runs_dir=tmp_path / "runs"))
    monkeypatch.setattr(live, "MIN_INTERVAL_S", 0.01)
    monkeypatch.setattr(llm, "vision_available", lambda: True)
    folder = tmp_path / "frames"
    folder.mkdir()
    for i in range(10):
        (folder / f"{i:03d}.jpg").write_bytes(_jpeg((200, 10 * i, 0) if i >= 3 else (0, 200, 10 * i)))

    def fake_detect(image):
        red = Image.open(io.BytesIO(image)).getpixel((0, 0))[0] > 100
        defects = ["spaghetti"] if red else []
        return detector.Detection(defects=defects, primary=defects[0] if defects else "none", model="e4b",
                                  latency_ms=3.0)

    monkeypatch.setattr(detector, "detect", fake_detect)
    return folder


def _wait(monitor, timeout=10):
    deadline = time.monotonic() + timeout
    while monitor.running and time.monotonic() < deadline:
        time.sleep(0.02)


def test_monitor_replay_end_to_end(replay):
    m = live.Monitor()
    session = m.start("replay", str(replay), interval_s=0.01, cfg=CFG)
    with pytest.raises(live.LiveError):
        m.start("replay", str(replay), interval_s=0.01, cfg=CFG)
    _wait(m)
    s = m.snapshot()
    assert s.status == "finished" and s.counts["frames"] == 10 and s.counts["positives"] == {"spaghetti": 7}
    assert [(a.defect, a.level) for a in s.alerts] == [("spaghetti", "pause_proposed")]
    # evidence frames are on disk; clean frames that are not the latest are not kept
    kept = {p.stem for p in (live.session_dir(s.id) / "frames").glob("*.jpg")}
    assert set(s.alerts[0].frames) <= kept and len(kept) == 7
    assert len(live.detections(s.id)) == 10 and live.load_session(s.id).status == "finished"
    assert len(m.evidence(s.id)) == 4
    assert session.id == s.id


def test_detector_errors_are_not_frames(replay, monkeypatch):
    monkeypatch.setattr(detector, "detect", lambda image: detector.Detection(error="timeout"))
    m = live.Monitor()
    m.start("replay", str(replay), interval_s=0.01, cfg=CFG)
    _wait(m)
    s = m.snapshot()
    assert s.counts["frames"] == 0 and s.counts["errors"] == 10 and s.alerts == []


def test_start_needs_the_detector(replay, monkeypatch):
    monkeypatch.setattr(llm, "vision_available", lambda: False)
    with pytest.raises(live.LiveError, match="detector"):
        live.Monitor().start("replay", str(replay))


def test_api_live(replay, monkeypatch):
    from fastapi.testclient import TestClient

    from printloop import api
    monkeypatch.setattr(live, "MONITOR", live.Monitor())
    client = TestClient(api.app)
    assert client.get("/api/live").json()["session"] is None
    assert client.post("/api/live/stop").status_code == 409
    assert client.post("/api/live/start", json={"source": "replay", "replay_dir": "/nope"}).status_code == 409
    res = client.post("/api/live/start", json={"source": "replay", "replay_dir": str(replay), "interval_s": 1})
    assert res.status_code == 200, res.text
    sid = res.json()["id"]
    res = client.post("/api/live/stop")
    assert res.json()["status"] == "stopped"
    body = client.get("/api/live").json()["session"]
    assert body["id"] == sid and not client.get("/api/live").json()["running"]
    if body["last"]:
        assert client.get(body["last"]["frame_url"]).headers["content-type"] == "image/jpeg"
    assert client.get("/api/live/sessions").json()[0]["id"] == sid
    assert client.get(f"/api/live/sessions/{sid}?detections=true").json()["detections"] is not None
    assert client.get(f"/api/live/frames/{sid}/../../etc").status_code == 404
    assert client.post("/api/live/pause").status_code == 409
    assert client.delete(f"/api/live/sessions/{sid}").json() == {"deleted": sid}
    assert client.get(f"/api/live/sessions/{sid}").status_code == 404


def test_identical_frames_count_once_as_evidence():
    p = policy.Policy(CFG)
    raised = [a for _ in range(4) for a in p.update("same0000frame000", ["spaghetti"], "t")]
    assert len(raised) == 1 and raised[0].frames == ["same0000frame000"]
