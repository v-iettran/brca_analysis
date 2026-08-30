"""Ollama LLM client implementing the shared protocol."""

from __future__ import annotations

import json
import re

import httpx

from pipeline_core.safety import check_safety

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text: str) -> str:
    """Drop chain-of-thought blocks that reasoning models emit before the answer."""
    return _THINK_RE.sub("", text).strip()


SYSTEM_PROMPT = (
    "You are a clinical research explanation assistant. You are given "
    "already-computed evidence and must describe it in plain, cautious "
    "language for a clinician. Never state a treatment recommendation, "
    "never say a patient is eligible for anything, never claim a cure or "
    "guarantee, and never invent a number that was not given to you."
)


# Larger first: this runs locally on one machine, and the grounding gate is what
# keeps an answer honest, so a stronger model mainly buys fluency.
# 8b first: on one laptop a 14b/26b first-token latency exceeds the request
# timeout, and the grounding gate — not model size — is what keeps an answer honest.
_MODEL_PREFERENCE = ("qwen3:8b", "qwen2.5:3b-instruct", "qwen3:14b", "gemma4:26b")


class OllamaLLMClient:
    provider_name = "ollama"

    def __init__(self, host: str, model: str, timeout: float):
        self.host = host.rstrip("/")
        self.model_name = model
        self.timeout = timeout
        self._resolved = False

    def installed_models(self) -> list[str]:
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            response.raise_for_status()
            return [str(m.get("name")) for m in response.json().get("models") or []]
        except (httpx.HTTPError, ValueError):
            return []

    def _resolve_model(self) -> None:
        """Fall back to an installed model when the configured one is absent.

        A configured-but-missing model fails silently: Ollama returns an error,
        `generate_text` reports "not used", and the copilot quietly serves its
        deterministic fallback for ever. That is exactly the failure this
        project keeps running into, so it is resolved rather than tolerated.
        """
        if self._resolved:
            return
        self._resolved = True
        installed = self.installed_models()
        if not installed or self.model_name in installed:
            return
        for preferred in _MODEL_PREFERENCE:
            if preferred in installed:
                self.model_name = preferred
                return
        self.model_name = installed[0]

    def is_available(self) -> bool:
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            if response.status_code != 200:
                return False
        except httpx.HTTPError:
            return False
        self._resolve_model()
        return True

    def _generate(self, prompt: str, system: str, temperature: float) -> str | None:
        self._resolve_model()
        try:
            response = httpx.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model_name,
                    "system": system,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return _strip_reasoning((response.json().get("response") or "").strip())
        except (httpx.HTTPError, ValueError):
            return None

    def generate_text(self, prompt: str, system: str, fallback: str = "") -> tuple[str, bool]:
        text = self._generate(prompt, system, temperature=0.2)
        if not text or check_safety(text):
            return fallback, False
        return text, True

    def generate_reviewable(self, prompt: str, system: str) -> tuple[str, bool]:
        """Return the raw answer for a caller that runs its own gate.

        `generate_text` reports an unsafe answer as "no answer", which makes a
        rejection indistinguishable from the model being unreachable. The
        copilot needs the text so its own review can tell the reader which of
        the two happened, and why.
        """
        text = self._generate(prompt, system, temperature=0.2)
        return (text or ""), bool(text)

    def generate_structured(self, prompt: str, system: str) -> tuple[dict | None, bool]:
        text = self._generate(prompt, system, temperature=0.0)
        if not text:
            return None, False
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None, False
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None, False
        if not isinstance(payload, dict):
            return None, False
        return payload, True
