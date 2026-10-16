"""Diagnosi del pezzo: Gemma 4 sulle foto (JSON schema) oppure dichiarazione dell'operatore.

Il modello classifica in una tassonomia chiusa, assegna la severità con la rubrica fissa e cita le
foto come evidenza. Non propone parametri: quello è compito di propose.py, vincolato dalla KB.
"""
from __future__ import annotations

from pathlib import Path

from printloop import llm
from printloop.config import LLM
from printloop.models import Diagnosis, Evidence, Finding
from printloop.taxonomy import DEFECT_CLASSES, DEFECTS, SEVERITY_PROMPT

SYSTEM_PROMPT = f"""You are the visual inspector of PrintLoop, a tool that fixes FDM 3D-printing defects by patching slicer presets.
You receive 1-4 photos of ONE printed part, plus context from the operator.

Classify what you see using ONLY these classes:
{chr(10).join(f"- {k}: {v['description']}" for k, v in DEFECTS.items())}

Rules:
- Report every defect you can actually see, each with a severity: {SEVERITY_PROMPT}
- confidence is your probability (0-1) that the defect class is correct.
- evidence: cite the photo file name and describe exactly what you see there (location, appearance).
- primary: the defect that most needs fixing; "none" if the part is fine.
- Do not guess causes or slicer settings. Do not invent defects that are not visible.
- If the photos are too blurry, too dark or do not show the relevant area, set needs_more_info=true and
  write question_for_operator in Italian (what photo to take). Otherwise question_for_operator is "".
- Answer with JSON only."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "defect": {"type": "string", "enum": list(DEFECT_CLASSES)},
                    "severity": {"type": "integer", "minimum": 0, "maximum": 3},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"photo": {"type": "string"}, "description": {"type": "string"}},
                            "required": ["photo", "description"],
                        },
                    },
                    "location": {"type": "string"},
                },
                "required": ["defect", "severity", "confidence", "evidence", "location"],
            },
        },
        "primary": {"type": "string", "enum": list(DEFECT_CLASSES)},
        "needs_more_info": {"type": "boolean"},
        "question_for_operator": {"type": "string"},
    },
    "required": ["findings", "primary", "needs_more_info", "question_for_operator"],
}


def _context(printer: str | None, material: str | None, note: str, previous: Diagnosis | None) -> str:
    lines = [f"Printer: {printer or 'unknown'}", f"Material: {material or 'unknown'}"]
    if note:
        lines.append(f"Operator note (may be in Italian): {note}")
    if previous is not None:
        lines.append(f"This is a reprint after a preset patch. Previous diagnosis: {previous.primary} "
                     f"(severity {previous.severity}). Judge the new photos on their own.")
    return "\n".join(lines)


def sanitize(raw: dict) -> dict:
    """Normalizza l'output del modello: classi valide, severità e confidenza nei range, primary coerente."""
    findings = []
    for f in raw.get("findings") or []:
        if f.get("defect") not in DEFECT_CLASSES:
            continue
        findings.append({
            "defect": f["defect"],
            "severity": max(0, min(3, int(round(float(f.get("severity", 0)))))),
            "confidence": max(0.0, min(1.0, float(f.get("confidence", 0)))),
            "evidence": [e for e in f.get("evidence") or [] if isinstance(e, dict) and "photo" in e and "description" in e],
            "location": str(f.get("location", "")),
        })
    findings = [f for f in findings if f["defect"] != "none" or len(findings) == 1]
    primary = raw.get("primary")
    defects = {f["defect"] for f in findings}
    if primary not in defects:
        real = [f for f in findings if f["defect"] not in ("none",)]
        primary = max(real, key=lambda f: (f["severity"], f["confidence"]))["defect"] if real else "none"
    return {"findings": findings, "primary": primary, "needs_more_info": bool(raw.get("needs_more_info")),
            "question_for_operator": str(raw.get("question_for_operator") or "")}


def diagnose_llm(photos: list[Path], printer: str | None = None, material: str | None = None, note: str = "",
                 previous: Diagnosis | None = None) -> Diagnosis:
    if not photos:
        raise ValueError("servono da 1 a 4 foto del pezzo")
    content: list[dict] = [{"type": "text", "text": _context(printer, material, note, previous)}]
    for photo in photos:
        content.append({"type": "text", "text": f"Photo: {photo.name}"})
        content.append(llm.image_part(photo))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]
    raw, latency = llm.chat_json(messages, SCHEMA, name="diagnosis")
    return Diagnosis(**sanitize(raw), source="llm", model=LLM.model, latency_ms=round(latency, 1), note=note)


def diagnose_operator(defect: str, severity: int, note: str = "", photos: list[str] | None = None) -> Diagnosis:
    """Diagnosi dichiarata dall'operatore: percorso offline e correzione umana della diagnosi del modello."""
    if defect not in DEFECT_CLASSES:
        raise ValueError(f"difetto sconosciuto: {defect}")
    evidence = [Evidence(photo=p, description="indicato dall'operatore") for p in (photos or [])]
    severity = 0 if defect == "none" else severity
    finding = Finding(defect=defect, severity=severity, confidence=1.0, evidence=evidence, location="")
    return Diagnosis(findings=[finding], primary=defect, source="operator", note=note)
