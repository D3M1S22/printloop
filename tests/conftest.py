"""Tests never call a real LLM, even when .env configures one: the tests that need it fake it."""
import pytest

from printloop import llm


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(llm, "describe", lambda: {"mode": "offline", "model": None, "base_url": None})
