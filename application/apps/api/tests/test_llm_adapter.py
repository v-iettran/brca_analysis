"""LLM factory fallback order."""

from __future__ import annotations

from app.adapters.llm.factory import NullLLMClient, get_llm_client, iter_llm_clients
from app.config import get_settings


def test_no_provider_yields_null_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    get_settings.cache_clear()
    assert list(iter_llm_clients()) == []
    client = get_llm_client()
    assert isinstance(client, NullLLMClient)
    text, used = client.generate_text("hello", "sys", fallback="fb")
    assert text == "fb"
    assert used is False
    get_settings.cache_clear()


def test_hosted_then_ollama_order(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("HOSTED_LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("HOSTED_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    get_settings.cache_clear()
    names = [client.provider_name for client in iter_llm_clients()]
    assert names[0] == "hosted"
    assert "ollama" in names
    get_settings.cache_clear()
