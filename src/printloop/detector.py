"""Defect detector: the fine-tuned Gemma 4 E4B (docs/printloop/07_VISION_MODEL.md), one image -> visible defect classes.

Used by Mode 1 on every live frame (live/) and by Mode 2 on every uploaded photo, as a hint for the 26B
(docs/printloop/09_MODE2_TWO_MODELS.md). The model was trained with exactly these strings (prompt version m1-v1,
source of truth: finetune/src/fdmft/prompt.py and finetune/configs/taxonomy.yaml): changing them invalidates the
measured accuracy. The app does not import finetune/; tests/test_detector.py checks the copy against it.
"""
from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import BaseModel

from printloop import llm
from printloop.config import VISION_LLM
from printloop.models import now_iso

PROMPT_VERSION = "m1-v1"
USER_TEXT = "Inspect this frame."

# Canonical order = urgency order for a running print: `primary` is the first item.
CLASSES: dict[str, str] = {
    "spaghetti": "A tangle of loose extruded filament instead of the part; the print failed and continued in mid-air.",
    "warping": "Corners or edges lifted from the bed, bottom not flat, part detached during the print.",
    "layer_shift": "Layers abruptly offset horizontally relative to the ones below, a step in the part.",
    "layer_separation": "Cracks or gaps between layers; layers split apart or delaminate.",
    "bridge_sagging": "Lines spanning unsupported gaps droop, sag, break or curl downwards under a bridge.",
    "overhang_curling": "Edges of angled overhangs curl upwards, look rough or drooped on the underside.",
    "stringing": "Thin hair-like strands or webs of filament between separate parts or across travel gaps.",
    "blobs": "Small zits, blobs or pimples of plastic on the surface of walls.",
    "under_extrusion": "Gaps between lines, thin or missing walls, porous or weak top surfaces, visible infill through skin.",
    "over_extrusion": "Blobby, bulging or rough walls, ridges on top surfaces, dimensions larger than intended.",
    "first_layer": "First layer problems: lines not fused, gaps, rough or squished bottom, poor adhesion.",
    "other": "A defect is visible but it does not fit any class above.",
}
ORDER: tuple[str, ...] = tuple(CLASSES)

_classes = "\n".join(f"- {c}: {d}" for c, d in CLASSES.items())
SYSTEM_PROMPT = f"""You are the visual inspector of a running FDM 3D print. You receive one image of the print.
Report the defects visible in the image using only these classes:
{_classes}
Rules: report only what is visible; an unfinished part is not a defect; list defects in the order above.
Answer with JSON only: {{"defects": [...], "primary": "<first defect or none>"}}"""

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"defects": {"type": "array", "items": {"type": "string", "enum": list(ORDER)}},
                         "primary": {"type": "string", "enum": [*ORDER, "none"]}},
          "required": ["defects", "primary"]}

# llama.cpp's Jinja template turns Gemma 4 thinking on by default: the model then spends the whole budget
# reasoning and writes no JSON. vLLM's Hugging Face template ignores the flag.
EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


class Detection(BaseModel):
    defects: list[str] = []
    primary: str = "none"
    model: str | None = None
    latency_ms: float | None = None
    prompt_version: str = PROMPT_VERSION
    error: str | None = None
    at: str = ""


def sort(defects) -> list[str]:
    present = set(defects)
    return [d for d in ORDER if d in present]


def frame_id(jpeg: bytes) -> str:
    return hashlib.sha1(jpeg).hexdigest()[:16]


def _jpeg(image: bytes | str | Path) -> bytes:
    """RGB JPEG q95, long side ≤ 1280 px (as the training images), EXIF orientation applied (phone photos)."""
    with Image.open(io.BytesIO(image) if isinstance(image, bytes) else image) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((VISION_LLM.max_image_px, VISION_LLM.max_image_px))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def messages(image: bytes | str | Path) -> list[dict]:
    b64 = base64.b64encode(_jpeg(image)).decode()
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                         {"type": "text", "text": USER_TEXT}]}]


def parse(raw: dict) -> tuple[list[str], str]:
    defects = sort(d for d in raw.get("defects") or [] if d in CLASSES)
    return defects, defects[0] if defects else "none"


def detect(image: bytes | str | Path) -> Detection:
    """Classifies one image. Never raises: errors come back in `Detection.error` (callers treat them as no answer)."""
    if not VISION_LLM.enabled:
        return Detection(error="detector not configured (VISION_LLM_BASE_URL)", at=now_iso())
    try:
        raw, latency = llm.chat_json(messages(image), SCHEMA, name="mode1", endpoint=VISION_LLM,
                                     retry_without_schema=False, telemetry=llm.VISION_TELEMETRY,
                                     extra_body=EXTRA_BODY)
    except Exception as exc:  # noqa: BLE001 - network, server, decoding: all mean "no answer for this image"
        return Detection(model=VISION_LLM.model, error=str(exc)[:300], at=now_iso())
    defects, primary = parse(raw)
    return Detection(defects=defects, primary=primary, model=VISION_LLM.model, latency_ms=round(latency, 1),
                     at=now_iso())
