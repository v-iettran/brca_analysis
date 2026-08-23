"""OpenAI-compatible hosted LLM adapter."""

from __future__ import annotations

import json

import httpx

from pipeline_core.safety import check_safety


class HostedLLMClient:
    provider_name = "hosted"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, max_tokens: int):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model_name)

    def _chat(self, prompt: str, system: str, temperature: float) -> str | None:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_name,
                    "temperature": temperature,
                    "max_tokens": self.max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        except (httpx.HTTPError, ValueError, IndexError, KeyError):
            return None

    def generate_text(self, prompt: str, system: str, fallback: str = "") -> tuple[str, bool]:
        text = self._chat(prompt, system, temperature=0.2)
        if not text or check_safety(text):
            return fallback, False
        return text, True

    def generate_structured(self, prompt: str, system: str) -> tuple[dict | None, bool]:
        text = self._chat(prompt, system, temperature=0.0)
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
