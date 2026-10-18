"""OpenAI-compatible LLM client: vLLM on AMD MI300X (Gemma 4) or, during development, a local llama-server.

Adapted from the MarginSwarm client, with images as data URLs. Records the telemetry (latency, tokens)
used by /api/health and by the benchmark. With no endpoint configured `available()` is False and the
pipeline uses operator diagnosis and rule-based proposals, and says so in the UI.
"""
from __future__ import annotations

import base64
import io
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI
from PIL import Image, ImageOps

from printloop.config import LLM, LOOP, VISION_LLM


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class Telemetry:
    calls: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, latency_ms: float, usage: Any | None) -> None:
        with self._lock:
            self.calls += 1
            self.latencies_ms.append(latency_ms)
            if usage is not None:
                self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

    def snapshot(self) -> dict:
        lat = sorted(self.latencies_ms)
        pct = (lambda q: round(lat[min(len(lat) - 1, int(q * len(lat)))], 1)) if lat else (lambda q: None)
        return {"calls": self.calls, "errors": self.errors, "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens, "latency_p50_ms": pct(0.5), "latency_p95_ms": pct(0.95)}


TELEMETRY = Telemetry()          # Mode 2 reasoner (26B)
VISION_TELEMETRY = Telemetry()   # E4B detector: kept apart so live frames do not flood the Mode 2 figures


def available() -> bool:
    return LLM.enabled


def vision_available() -> bool:
    return VISION_LLM.enabled


def describe() -> dict:
    if not LLM.enabled:
        return {"mode": "offline", "model": None, "base_url": None}
    return {"mode": "llm", "model": LLM.model, "base_url": LLM.base_url}


def describe_vision() -> dict:
    if not VISION_LLM.enabled:
        return {"mode": "off", "model": None, "base_url": None}
    return {"mode": "on", "model": VISION_LLM.model, "base_url": VISION_LLM.base_url}


def image_part(path: str | Path, max_px: int | None = None) -> dict:
    """Photo resized (long side ≤ max_px), oriented by EXIF, as a JPEG data URL."""
    max_px = max_px or LOOP.max_image_px
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    data = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


def _json_from_text(text: str) -> Any:
    """Extracts the first JSON object from a reply (for endpoints without structured output)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"no JSON in the reply: {text[:200]}")
    return json.loads(match.group(0))


def chat_json(messages: list[dict], schema: dict, name: str = "output", temperature: float = 0.0,
              max_tokens: int | None = None, *, endpoint=None, retry_without_schema: bool = True,
              telemetry: Telemetry | None = None, extra_body: dict | None = None) -> tuple[dict, float]:
    """Call with output constrained to a JSON schema. Returns (object, latency ms).

    `endpoint` defaults to the Mode 2 reasoner (LLM_*); the detector passes VISION_LLM. If the endpoint rejects
    `response_format` (e.g. old llama-server) it retries without it and looks for the JSON in the text, unless
    `retry_without_schema` is off (live frames: the next tick is the retry).
    """
    cfg = endpoint or LLM
    tel = telemetry or TELEMETRY
    if not cfg.enabled:
        raise LLMUnavailable(f"no endpoint configured for {cfg.model}")
    max_tokens = max_tokens or cfg.max_tokens
    client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key or "EMPTY", timeout=cfg.timeout_s,
                    max_retries=1 if retry_without_schema else 0)
    last: Exception | None = None
    for use_schema in ((True, False) if retry_without_schema else (True,)):
        try:
            t0 = time.perf_counter()
            kwargs = {"response_format": {"type": "json_schema",
                                          "json_schema": {"name": name, "schema": schema, "strict": True}}} if use_schema else {}
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = client.chat.completions.create(model=cfg.model, messages=messages, temperature=temperature,
                                                  max_tokens=max_tokens, **kwargs)
            latency = (time.perf_counter() - t0) * 1000
            tel.record(latency, resp.usage)
            if resp.choices[0].finish_reason == "length":
                raise ValueError(f"reply truncated at {max_tokens} tokens: increase the max_tokens of {cfg.model}")
            return _json_from_text(resp.choices[0].message.content), latency
        except Exception as exc:  # noqa: BLE001 - try the next variant
            tel.errors += 1
            last = exc
    raise LLMUnavailable(f"LLM call failed ({cfg.model}): {last}")
