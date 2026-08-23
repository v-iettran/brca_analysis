"""Select hosted LLM, Ollama, or none."""

from __future__ import annotations

from app.adapters.llm.hosted_client import HostedLLMClient
from app.adapters.llm.ollama_client import OllamaLLMClient
from app.config import get_settings


class NullLLMClient:
    provider_name = "none"
    model_name = "deterministic"

    def is_available(self) -> bool:
        return False

    def generate_text(self, prompt: str, system: str, fallback: str = "") -> tuple[str, bool]:
        return fallback, False

    def generate_structured(self, prompt: str, system: str) -> tuple[dict | None, bool]:
        return None, False


def iter_llm_clients():
    """Hosted, then Ollama, skipping unconfigured providers."""
    settings = get_settings()
    if settings.llm_provider != "none" and settings.llm_provider in {"auto", "hosted"}:
        if settings.hosted_llm_base_url and settings.hosted_llm_api_key:
            yield HostedLLMClient(
                settings.hosted_llm_base_url,
                settings.hosted_llm_api_key,
                settings.hosted_llm_model,
                settings.hosted_llm_timeout_seconds,
                settings.llm_max_output_tokens,
            )
    if settings.llm_provider != "none" and settings.llm_provider in {"auto", "ollama"} and settings.ollama_enabled:
        yield OllamaLLMClient(settings.ollama_host, settings.ollama_model, settings.ollama_timeout_seconds)


def get_llm_client():
    """Return the first configured client, else a null client."""
    settings = get_settings()
    for client in iter_llm_clients():
        if settings.llm_provider in {"hosted", "ollama"} or client.is_available() or client.provider_name == "hosted":
            return client
    return NullLLMClient()
