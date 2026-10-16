"""I test non chiamano mai un LLM reale, anche se .env lo configura: i test che servono lo simulano."""
import pytest

from printloop import llm


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(llm, "describe", lambda: {"mode": "offline", "model": None, "base_url": None})
