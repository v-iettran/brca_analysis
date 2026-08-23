"""Local Ollama adapter (compat wrapper around the shared LLM protocol)."""

from __future__ import annotations

from app.adapters.llm.factory import get_llm_client
from app.adapters.llm.ollama_client import SYSTEM_PROMPT, OllamaLLMClient
from app.config import get_settings

settings = get_settings()


class OllamaUnavailableError(RuntimeError):
    pass


def is_ollama_reachable(host: str, timeout: float = 2.0) -> bool:
    return OllamaLLMClient(host, settings.ollama_model, timeout).is_available()


def generate_explanation(
    host: str, model: str, prompt: str, timeout: float = 30.0, fallback: str = ""
) -> tuple[str, bool]:
    client = OllamaLLMClient(host, model, timeout)
    return client.generate_text(prompt, SYSTEM_PROMPT, fallback=fallback)


def classify_stance_with_llm(
    host: str, model: str, excerpt: str, timeout: float = 20.0
) -> str | None:
    prompt = (
        "Classify this excerpt about a cancer drug as exactly one word - "
        "supporting, conflicting, neutral, or unclear - with respect to "
        "whether it supports using the drug. Respond with only that one "
        f"word.\n\nExcerpt: {excerpt[:800]}"
    )
    text, used = OllamaLLMClient(host, model, timeout).generate_text(prompt, SYSTEM_PROMPT, fallback="")
    if not used:
        client = get_llm_client()
        text, used = client.generate_text(prompt, SYSTEM_PROMPT, fallback="")
        if not used:
            return None
    label = "".join(ch for ch in text.strip().lower() if ch.isalpha())
    return label if label in {"supporting", "conflicting", "neutral", "unclear"} else None
