"""Ollama LLM client implementing the shared protocol."""

from __future__ import annotations

import json

import httpx

from pipeline_core.safety import check_safety

SYSTEM_PROMPT = (
    "You are a clinical research explanation assistant. You are given "
    "already-computed evidence and must describe it in plain, cautious "
    "language for a clinician. Never state a treatment recommendation, "
    "never say a patient is eligible for anything, never claim a cure or "
    "guarantee, and never invent a number that was not given to you."
)


class OllamaLLMClient:
    provider_name = "ollama"

    def __init__(self, host: str, model: str, timeout: float):
        self.host = host.rstrip("/")
        self.model_name = model
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=2.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _generate(self, prompt: str, system: str, temperature: float) -> str | None:
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
            return (response.json().get("response") or "").strip()
        except (httpx.HTTPError, ValueError):
            return None

    def generate_text(self, prompt: str, system: str, fallback: str = "") -> tuple[str, bool]:
        text = self._generate(prompt, system, temperature=0.2)
        if not text or check_safety(text):
            return fallback, False
        return text, True

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
