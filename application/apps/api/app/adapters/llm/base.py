"""Provider-neutral LLM client protocol."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    provider_name: str
    model_name: str

    def is_available(self) -> bool: ...

    def generate_text(self, prompt: str, system: str, fallback: str = "") -> tuple[str, bool]: ...

    def generate_structured(self, prompt: str, system: str) -> tuple[dict | None, bool]: ...
