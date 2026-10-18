"""Detector contract: the app's copy of the m1-v1 prompt must match the one the model was trained with."""
import importlib
import io
import sys

import pytest
from PIL import Image

from printloop import config, detector, llm

FINETUNE_SRC = config.ROOT / "finetune" / "src"


@pytest.mark.skipif(not (FINETUNE_SRC / "fdmft" / "prompt.py").exists(), reason="finetune/ not present")
def test_prompt_matches_finetune():
    pytest.importorskip("yaml")
    sys.path.insert(0, str(FINETUNE_SRC))
    try:
        prompt = importlib.import_module("fdmft.prompt")
        taxonomy = importlib.import_module("fdmft.taxonomy")
    finally:
        sys.path.remove(str(FINETUNE_SRC))
    tax = taxonomy.load()
    assert detector.SYSTEM_PROMPT == prompt.system_prompt(tax)
    assert detector.USER_TEXT == prompt.USER_TEXT
    assert detector.PROMPT_VERSION == prompt.PROMPT_VERSION
    assert detector.SCHEMA == prompt.output_schema(tax)


def _jpeg(size=(1920, 1080)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 120, 120)).save(buf, "JPEG")
    return buf.getvalue()


def test_request_shape_and_parsing(monkeypatch):
    monkeypatch.setattr(detector, "VISION_LLM", config.VisionLLMConfig(base_url="http://x/v1", model="e4b"))
    seen = {}

    def fake(messages, schema, name, **kw):
        seen.update(messages=messages, name=name, **kw)
        return {"defects": ["stringing", "spaghetti", "made_up"], "primary": "stringing"}, 12.0

    monkeypatch.setattr(llm, "chat_json", fake)
    det = detector.detect(_jpeg())
    assert det.defects == ["spaghetti", "stringing"] and det.primary == "spaghetti" and det.error is None
    assert seen["name"] == "mode1" and seen["retry_without_schema"] is False
    assert seen["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    user = seen["messages"][1]["content"]
    assert user[0]["type"] == "image_url" and user[1] == {"type": "text", "text": "Inspect this frame."}
    # the image is resized to the training size (long side 1280)
    import base64
    data = base64.b64decode(user[0]["image_url"]["url"].split(",", 1)[1])
    assert max(Image.open(io.BytesIO(data)).size) == 1280


def test_errors_never_raise(monkeypatch):
    monkeypatch.setattr(detector, "VISION_LLM", config.VisionLLMConfig(base_url=None))
    assert "not configured" in detector.detect(_jpeg()).error
    monkeypatch.setattr(detector, "VISION_LLM", config.VisionLLMConfig(base_url="http://x/v1"))

    def boom(*a, **k):
        raise llm.LLMUnavailable("down")

    monkeypatch.setattr(llm, "chat_json", boom)
    det = detector.detect(_jpeg())
    assert det.error and det.defects == [] and det.primary == "none"
