"""Temporal filter and alert policy for Mode 1 (08_MODE1_LIVE.md §5). Pure logic: no I/O, easy to test.

One frame never triggers anything: a class must persist for k of the last n inferred frames. Failures that justify
pausing raise `pause_proposed` (the pause is sent only after an operator click); quality defects raise `warning`.
An alert clears after `clear_n` consecutive frames without its class.
"""
from __future__ import annotations

import uuid
from collections import deque

from printloop.config import Mode1Config
from printloop.models import LiveAlert

PAUSE = ("spaghetti", "warping", "layer_shift", "other")
WARN = ("layer_separation", "stringing", "blobs", "under_extrusion", "over_extrusion", "first_layer")
LOG_ONLY = ("bridge_sagging", "overhang_curling")   # no training data: counted, never alerted
MAX_EVIDENCE = 5


def gated(defect: str, layer: int | None) -> bool:
    """Classes that make no sense at this height (only when the printer reports the layer)."""
    if layer is None:
        return False
    if defect == "first_layer":
        return layer > 2
    if defect in ("stringing", "layer_shift"):
        return layer < 3
    return False


class Policy:
    def __init__(self, cfg: Mode1Config):
        self.cfg = cfg
        self.windows: dict[str, deque] = {}
        self.positive_frames: dict[str, deque] = {}
        self.misses: dict[str, int] = {}
        self.active: dict[str, LiveAlert] = {}
        self.alerts: list[LiveAlert] = []

    def thresholds(self) -> dict[str, int]:
        c = self.cfg
        return {"pause_k": c.pause_k, "pause_n": c.pause_n, "alert_k": c.alert_k, "alert_n": c.alert_n,
                "clear_n": c.clear_n}

    def _kn(self, defect: str) -> tuple[int, int, str]:
        if defect in PAUSE:
            return self.cfg.pause_k, self.cfg.pause_n, "pause_proposed"
        return self.cfg.alert_k, self.cfg.alert_n, "warning"

    def update(self, frame_id: str, defects: list[str], at: str, layer: int | None = None) -> list[LiveAlert]:
        """Feeds one inferred frame; returns the alerts raised or cleared by it."""
        changed = []
        for defect in PAUSE + WARN:
            k, n, level = self._kn(defect)
            window = self.windows.setdefault(defect, deque(maxlen=n))
            frames = self.positive_frames.setdefault(defect, deque(maxlen=n))
            present = defect in defects and not gated(defect, layer)
            window.append(present)
            if present:
                frames.append(frame_id)
                self.misses[defect] = 0
            else:
                self.misses[defect] = self.misses.get(defect, 0) + 1
            alert = self.active.get(defect)
            if alert is None:
                if sum(window) >= k:
                    unique = list(dict.fromkeys(frames))  # identical frames (a static scene) count once as evidence
                    alert = LiveAlert(id=uuid.uuid4().hex[:8], defect=defect, level=level, since=at,
                                      frames=unique[-(MAX_EVIDENCE - 1):])
                    self.active[defect] = alert
                    self.alerts.append(alert)
                    changed.append(alert)
            elif present:
                if frame_id not in alert.frames:  # keep the frames that raised it + the most recent positive
                    alert.frames = (alert.frames[:MAX_EVIDENCE - 1] + [frame_id])[:MAX_EVIDENCE]
            elif self.misses[defect] >= self.cfg.clear_n:
                alert.cleared_at = at
                del self.active[defect]
                window.clear()
                frames.clear()
                changed.append(alert)
        return changed

    def dismiss(self, alert_id: str, reason: str = "") -> LiveAlert:
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.dismissed = True
                alert.dismiss_reason = reason
                return alert
        raise KeyError(alert_id)

    def evidence(self) -> list[str]:
        """Frame ids of the alerts, newest alerts first, without duplicates."""
        out: list[str] = []
        for alert in reversed(self.alerts):
            for fid in reversed(alert.frames):
                if fid not in out:
                    out.append(fid)
        return out
