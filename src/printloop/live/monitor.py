"""Mode 1 monitor (08_MODE1_LIVE.md §3, §6): one session at a time, a background thread in the API process.

Every `interval_s` it takes the latest frame, asks the detector, feeds the temporal filter and writes everything to
runs/live/<session>/: session.json, detections.jsonl (one row per inference) and frames/ (frames with a detected
defect, the latest frame, or every frame with record_all). It never takes the case or API locks: it touches a case
only through `evidence()`, which the API passes to the normal photo upload.
"""
from __future__ import annotations

import json
import re
import shutil
import statistics
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from printloop import config, detector, llm
from printloop.live.policy import Policy
from printloop.live.sources import open_source, wait_first_frame
from printloop.models import LiveDetection, LiveSession, now_iso


MIN_INTERVAL_S = 1.0  # one Q8_0 E4B answers in ~0.75 s; tests lower it


class LiveError(ValueError):
    """Operation not possible on the monitor (already running, nothing to stop, bad source)."""


def live_dir() -> Path:
    path = config.LOOP.runs_dir / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_dir(session_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        raise KeyError(session_id)
    return live_dir() / session_id


def load_session(session_id: str) -> LiveSession:
    path = session_dir(session_id) / "session.json"
    if not path.exists():
        raise KeyError(session_id)
    return LiveSession.model_validate_json(path.read_text(encoding="utf-8"))


def list_sessions() -> list[LiveSession]:
    out = []
    for path in live_dir().glob("*/session.json"):
        try:
            out.append(LiveSession.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(out, key=lambda s: s.started_at, reverse=True)


def detections(session_id: str) -> list[dict]:
    path = session_dir(session_id) / "detections.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def frame_path(session_id: str, frame: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", frame):
        raise KeyError(frame)
    path = session_dir(session_id) / "frames" / f"{frame}.jpg"
    if not path.exists():
        raise KeyError(frame)
    return path


class Monitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.session: LiveSession | None = None
        self.policy: Policy | None = None
        self._source = None
        self._latencies: list[float] = []
        self._calls = 0
        self._errors = 0

    # --- control -----------------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, source: str | None = None, replay_dir: str | None = None, url: str | None = None,
              interval_s: float | None = None, case_id: str | None = None, record_all: bool | None = None,
              cfg: config.Mode1Config | None = None) -> LiveSession:
        with self._lock:
            if self.running:
                raise LiveError("a live session is already running: stop it first")
            if not llm.vision_available():
                raise LiveError("the defect detector is not configured (VISION_LLM_BASE_URL)")
            base = cfg or config.MODE1
            cfg = replace(base, source=source or base.source, replay_dir=replay_dir or base.replay_dir,
                          snapshot_url=url or base.snapshot_url,
                          interval_s=max(MIN_INTERVAL_S, float(interval_s or base.interval_s)),
                          record_all=base.record_all if record_all is None else record_all)
            src = open_source(cfg.source, cfg.replay_dir, cfg.snapshot_url, cfg.printer_ip, cfg.printer_access_code)
            self._source = src
            self.policy = Policy(cfg)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.session = LiveSession(id=f"{stamp}-{uuid.uuid4().hex[:4]}", source={"kind": src.kind, "detail": src.detail},
                                       interval_s=cfg.interval_s, record_all=cfg.record_all, case_id=case_id,
                                       thresholds=self.policy.thresholds())
            self._latencies, self._calls, self._errors = [], 0, 0
            (session_dir(self.session.id) / "frames").mkdir(parents=True)
            self._persist()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="live-monitor", daemon=True)
            self._thread.start()
            return self.session

    def stop(self, status: str = "stopped") -> LiveSession:
        thread = self._thread
        if self.session is None or not self.running:
            raise LiveError("no live session is running")
        self._stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=60)
        with self._lock:
            self._finish(status)
            return self.session

    def dismiss(self, alert_id: str, reason: str = "") -> LiveSession:
        with self._lock:
            if self.session is None or self.policy is None:
                raise LiveError("no live session")
            try:
                self.policy.dismiss(alert_id, reason)
            except KeyError as exc:
                raise LiveError(f"alert {alert_id} not found") from exc
            self.session.alerts = self.policy.alerts
            self._persist()
            return self.session

    def snapshot(self) -> LiveSession | None:
        with self._lock:
            return self.session.model_copy(deep=True) if self.session else None

    # --- loop --------------------------------------------------------------------------------------------

    def _run(self) -> None:
        assert self.session is not None
        interval = self.session.interval_s
        if self._source.kind != "replay":
            wait_first_frame(self._source)
        next_tick = time.monotonic()
        last_id = None
        while not self._stop.is_set():
            now = time.monotonic()
            if now < next_tick:
                self._stop.wait(next_tick - now)
                continue
            missed = int((now - next_tick) // interval)
            next_tick += (missed + 1) * interval  # inference slower than the interval: skip, never pile up
            with self._lock:
                self.session.counts["skipped"] += missed
            frame = self._source.latest()
            if frame is None:
                if self._source.exhausted:
                    with self._lock:
                        self._finish("finished")
                    return
                self._count("skipped")
                continue
            if frame.id == last_id and self._source.kind != "replay":  # the camera has not produced a new frame
                self._count("skipped")
                continue
            last_id = frame.id
            det = detector.detect(frame.jpeg)
            self._record(frame, det)

    def _count(self, key: str) -> None:
        with self._lock:
            self.session.counts[key] += 1

    def _record(self, frame, det) -> None:
        with self._lock:
            s = self.session
            row = LiveDetection(frame_id=frame.id, name=frame.name, taken_at=frame.taken_at, defects=det.defects,
                                primary=det.primary, model=det.model, latency_ms=det.latency_ms, error=det.error)
            root = session_dir(s.id)
            with open(root / "detections.jsonl", "a", encoding="utf-8") as fh:
                fh.write(row.model_dump_json() + "\n")
            self._calls += 1
            if det.error:  # errors are not frames for the filter: the next tick is the retry
                self._errors += 1
                s.counts["errors"] += 1
            else:
                self._latencies.append(det.latency_ms or 0.0)
                s.counts["frames"] += 1
                for d in det.defects:
                    s.counts["positives"][d] = s.counts["positives"].get(d, 0) + 1
                self.policy.update(frame.id, det.defects, frame.taken_at, s.printer.get("layer_num"))
                s.alerts = self.policy.alerts
            # Keep frames with a defect (possible evidence), the latest one, or all of them with record_all.
            (root / "frames" / f"{frame.id}.jpg").write_bytes(frame.jpeg)
            previous = s.last
            if previous and previous.frame_id != frame.id and not s.record_all and not previous.defects:
                (root / "frames" / f"{previous.frame_id}.jpg").unlink(missing_ok=True)
            s.last = row
            self._persist()

    def _finish(self, status: str) -> None:
        if self.session is None or self.session.ended_at:
            return
        self.session.status = status  # type: ignore[assignment]
        self.session.ended_at = now_iso()
        if self._source is not None:
            self._source.close()
        self._persist()

    def _persist(self) -> None:
        s = self.session
        lat = sorted(self._latencies)
        s.detector = {"model": detector.VISION_LLM.model, "calls": self._calls, "errors": self._errors,
                      "latency_p50_ms": round(statistics.median(lat), 1) if lat else None}
        path = session_dir(s.id) / "session.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(s.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    # --- evidence ----------------------------------------------------------------------------------------

    def evidence(self, session_id: str, frames: list[str] | None = None, limit: int = 4) -> list[tuple[str, bytes]]:
        """Evidence frames as (file name, JPEG) for a case upload: the given ones, or the alerts' newest first."""
        session = self.session if self.session and self.session.id == session_id else load_session(session_id)
        if not frames:
            frames = []
            for alert in reversed(session.alerts):
                for fid in reversed(alert.frames):
                    if fid not in frames:
                        frames.append(fid)
            if not frames and session.last:
                frames = [session.last.frame_id]
        out = []
        for fid in frames[:limit]:
            out.append((f"live_{fid}.jpg", frame_path(session_id, fid).read_bytes()))
        if not out:
            raise LiveError("this session has no evidence frames")
        return out


def delete_session(monitor: Monitor, session_id: str) -> None:
    if monitor.session and monitor.session.id == session_id and monitor.running:
        raise LiveError("stop the session before deleting it")
    load_session(session_id)
    shutil.rmtree(session_dir(session_id))


MONITOR = Monitor()
