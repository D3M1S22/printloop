"""Data models shared by pipeline, API and audit (contracts in docs/printloop/05_API.md)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from printloop.taxonomy import DEFECT_CLASSES

DefectClass = Literal[DEFECT_CLASSES]  # type: ignore[valid-type]
CaseState = Literal["awaiting_photos", "ready", "needs_info", "diagnosed", "awaiting_approval", "escalated", "done"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Evidence(BaseModel):
    photo: str
    description: str


class Finding(BaseModel):
    defect: DefectClass
    severity: int = Field(ge=0, le=3)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []
    location: str = ""


class PhotoDetection(BaseModel):
    """Answer of the E4B detector for one uploaded photo (docs/printloop/09_MODE2_TWO_MODELS.md)."""
    photo: str
    defects: list[str] = []
    primary: str = "none"
    model: str | None = None
    latency_ms: float | None = None
    error: str | None = None


class DetectorSummary(BaseModel):
    """Detector classes over all photos and whether the 26B agrees with them."""
    defects: list[str] = []
    primary: str = "none"
    agreement: Literal["agree", "disagree", "unavailable"] = "unavailable"
    photos: int = 0


class Diagnosis(BaseModel):
    findings: list[Finding] = []
    primary: DefectClass = "none"
    needs_more_info: bool = False
    question_for_operator: str = ""
    source: Literal["llm", "operator"] = "llm"
    model: str | None = None
    latency_ms: float | None = None
    note: str = ""
    detector: DetectorSummary | None = None
    at: str = Field(default_factory=now_iso)

    def primary_finding(self) -> Finding | None:
        for finding in self.findings:
            if finding.defect == self.primary:
                return finding
        return None

    @property
    def severity(self) -> int:
        finding = self.primary_finding()
        return finding.severity if finding else 0

    @property
    def confidence(self) -> float:
        finding = self.primary_finding()
        return finding.confidence if finding else 1.0


class Change(BaseModel):
    key: str                                   # KB key (or real key, for companions)
    before: float | str | None = None
    after: float | str
    reason: str = ""
    real: dict[str, float | str] = {}          # real project keys -> value written
    companion: bool = False                    # added by the validator (e.g. brim_type)
    label: str = ""
    unit: str = ""


class Attempt(BaseModel):
    source: Literal["llm", "rules", "operator"]
    changes: list[Change]
    stage: Literal["validation", "slicing", "preflight"]
    reason: str


class Proposal(BaseModel):
    defect: DefectClass
    changes: list[Change]
    rationale: str = ""
    expected_effect: str = ""
    source: Literal["llm", "rules", "operator"] = "rules"
    model: str | None = None
    latency_ms: float | None = None
    rejected_attempts: list[Attempt] = []
    at: str = Field(default_factory=now_iso)


class Validation(BaseModel):
    ok: bool
    errors: list[str] = []
    warnings: list[str] = []


class Check(BaseModel):
    check: str
    key: str | None = None
    target: str = ""            # feature or config key being checked
    before: float | None = None
    after: float | None = None
    expected: str = ""
    status: Literal["pass", "fail", "n/a"] = "pass"
    detail: str = ""


class Preflight(BaseModel):
    ok: bool
    checks: list[Check] = []
    limits: list[Check] = []
    side_effects: dict[str, Any] = {}


class Decision(BaseModel):
    approved: bool
    reason: str = ""
    actor: str = "operator"
    edited: bool = False
    override_preflight: bool = False
    stop: bool = False
    at: str = Field(default_factory=now_iso)


class Confirmation(BaseModel):
    """The operator confirmed that the reprint is good, closing the case."""
    note: str = ""
    actor: str = "operator"
    at: str = Field(default_factory=now_iso)


class Iteration(BaseModel):
    n: int
    project: str                     # 3MF printed in this iteration (relative to the case folder)
    source_gcode: str                # G-code of that print: the "before" of the pre-flight
    photos: list[str] = []
    detections: list[PhotoDetection] = []   # E4B labels, one per photo, filled at upload (best effort)
    note: str = ""
    diagnosis: Diagnosis | None = None
    proposal: Proposal | None = None
    validation: Validation | None = None
    preflight: Preflight | None = None
    patched_project: str | None = None
    sliced_3mf: str | None = None    # 3MF with G-code to print if the patch is approved
    slice: dict[str, Any] | None = None
    decision: Decision | None = None
    rejected: list[dict[str, Any]] = []  # proposals rejected by the operator, with the reason
    confirmed: Confirmation | None = None


class Case(BaseModel):
    id: str
    name: str
    state: CaseState = "awaiting_photos"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    printer: str | None = None
    material: str | None = None
    process: str | None = None
    max_iterations: int = 3
    baseline: dict[str, Any] = {}
    iterations: list[Iteration] = []
    rejected_keys: list[str] = []
    outcome: Literal["fixed", "no_defect", "escalated", "stopped"] | None = None
    message: str = ""

    @property
    def current(self) -> Iteration:
        return self.iterations[-1]


# --- Mode 1: live monitoring (docs/printloop/08_MODE1_LIVE.md) ---------------------------------------------

class LiveDetection(BaseModel):
    frame_id: str                     # sha1 of the JPEG (16 hex)
    name: str = ""                    # file name for replayed frames
    taken_at: str
    layer_num: int | None = None
    progress: float | None = None     # mc_percent
    defects: list[str] = []
    primary: str = "none"
    model: str | None = None
    latency_ms: float | None = None
    error: str | None = None


class LiveAlert(BaseModel):
    id: str
    defect: str
    level: Literal["warning", "pause_proposed"]
    since: str
    frames: list[str] = []            # frame ids kept as evidence
    cleared_at: str | None = None
    dismissed: bool = False
    dismiss_reason: str = ""


class LiveSession(BaseModel):
    id: str
    status: Literal["running", "stopped", "finished", "error"] = "running"
    source: dict[str, Any] = {}       # {"kind": "replay"|"p1s"|"url", "detail": ...}
    interval_s: float = 10
    record_all: bool = False
    case_id: str | None = None
    started_at: str = Field(default_factory=now_iso)
    ended_at: str | None = None
    error: str = ""
    thresholds: dict[str, int] = {}
    printer: dict[str, Any] = {"linked": False}
    detector: dict[str, Any] = {}     # model, calls, errors, latency_p50_ms
    last: LiveDetection | None = None
    alerts: list[LiveAlert] = []
    counts: dict[str, Any] = {"frames": 0, "skipped": 0, "errors": 0, "positives": {}}
