"""Client LLM OpenAI-compatibile: vLLM su AMD MI300X (Gemma 4) o, in sviluppo, llama-server locale.

Ripreso dal client di MarginSwarm, con le immagini come data URL. Registra la telemetria (latenza,
token) usata da /api/health e dal benchmark. Se nessun endpoint è configurato `available()` è False e la
pipeline usa diagnosi dell'operatore e proposta a regole, dichiarandolo in UI.
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

from printloop.config import LLM, LOOP


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


TELEMETRY = Telemetry()


def available() -> bool:
    return LLM.enabled


def describe() -> dict:
    if not LLM.enabled:
        return {"mode": "offline", "model": None, "base_url": None}
    return {"mode": "llm", "model": LLM.model, "base_url": LLM.base_url}


def image_part(path: str | Path, max_px: int | None = None) -> dict:
    """Foto ridimensionata (lato lungo ≤ max_px), orientata secondo EXIF, come data URL JPEG."""
    max_px = max_px or LOOP.max_image_px
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    data = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


def _json_from_text(text: str) -> Any:
    """Estrae il primo oggetto JSON da una risposta (per endpoint senza structured output)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"nessun JSON nella risposta: {text[:200]}")
    return json.loads(match.group(0))


def chat_json(messages: list[dict], schema: dict, name: str = "output", temperature: float = 0.0,
              max_tokens: int | None = None) -> tuple[dict, float]:
    """Chiamata con output vincolato a JSON schema. Restituisce (oggetto, latenza ms).

    Se l'endpoint rifiuta `response_format` (es. llama-server vecchi) ritenta senza e cerca il JSON nel testo.
    """
    if not LLM.enabled:
        raise LLMUnavailable("nessun endpoint LLM configurato (LLM_BASE_URL)")
    client = OpenAI(base_url=LLM.base_url, api_key=LLM.api_key or "EMPTY", timeout=LLM.timeout_s, max_retries=1)
    last: Exception | None = None
    for use_schema in (True, False):
        try:
            t0 = time.perf_counter()
            kwargs = {"response_format": {"type": "json_schema",
                                          "json_schema": {"name": name, "schema": schema, "strict": True}}} if use_schema else {}
            resp = client.chat.completions.create(model=LLM.model, messages=messages, temperature=temperature,
                                                  max_tokens=max_tokens or LLM.max_tokens, **kwargs)
            latency = (time.perf_counter() - t0) * 1000
            TELEMETRY.record(latency, resp.usage)
            if resp.choices[0].finish_reason == "length":
                raise ValueError(f"risposta troncata a {max_tokens or LLM.max_tokens} token: aumentare LLM_MAX_TOKENS")
            return _json_from_text(resp.choices[0].message.content), latency
        except Exception as exc:  # noqa: BLE001 - si prova la variante successiva
            TELEMETRY.errors += 1
            last = exc
    raise LLMUnavailable(f"chiamata LLM fallita: {last}")
