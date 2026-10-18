"""Mode 1 prompt, target, output schema and parsing, shared by training, evaluation and serving.

The fine-tuned model was trained with exactly this system prompt, user text and answer format: a client
(PrintLoop Mode 1) must send the same strings to get the measured accuracy. Changing them invalidates the
comparisons: bump PROMPT_VERSION.
"""
from __future__ import annotations

import json
import re

from fdmft.taxonomy import Taxonomy

PROMPT_VERSION = "m1-v1"
USER_TEXT = "Inspect this frame."


def system_prompt(tax: Taxonomy) -> str:
    classes = "\n".join(f"- {c}: {tax.classes[c]}" for c in tax.order)
    return f"""You are the visual inspector of a running FDM 3D print. You receive one image of the print.
Report the defects visible in the image using only these classes:
{classes}
Rules: report only what is visible; an unfinished part is not a defect; list defects in the order above.
Answer with JSON only: {{"defects": [...], "primary": "<first defect or none>"}}"""


def target(defects: list[str], tax: Taxonomy) -> str:
    """Expected answer: defects in the canonical order and the primary (first) one, `none` if empty."""
    ordered = tax.sort(defects)
    return json.dumps({"defects": ordered, "primary": tax.primary(ordered)}, separators=(", ", ": "))


def messages(image, tax: Taxonomy, defects: list[str] | None = None) -> list[dict]:
    """Conversation in the chat-template format of the Gemma 4 processor (image before the text)."""
    msgs = [
        {"role": "system", "content": [{"type": "text", "text": system_prompt(tax)}]},
        {"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": USER_TEXT}]},
    ]
    if defects is not None:
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": target(defects, tax)}]})
    return msgs


def output_schema(tax: Taxonomy) -> dict:
    """JSON schema for constrained decoding (`response_format` of an OpenAI-compatible server)."""
    return {"type": "object", "additionalProperties": False,
            "properties": {"defects": {"type": "array", "items": {"type": "string", "enum": list(tax.order)}},
                           "primary": {"type": "string", "enum": [*tax.order, "none"]}},
            "required": ["defects", "primary"]}


def parse(text: str, tax: Taxonomy) -> tuple[bool, list[str]]:
    """(valid and conforming JSON, predicted defects). Unknown classes make the answer non-conforming."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return False, []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return False, []
    defects = data.get("defects")
    if not isinstance(defects, list) or not all(isinstance(d, str) for d in defects):
        return False, []
    valid = all(d in tax.order for d in defects) and data.get("primary") in (*tax.order, "none")
    return valid, tax.sort([d for d in defects if d in tax.order])
