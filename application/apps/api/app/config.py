"""API runtime configuration.

Secrets are read only from the environment, never hard-coded or logged.
Public demo mode accepts only synthetic patients and never persists RNA.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from pipeline_core.config import DB_PATH


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MOFA-Guided Oncology Research Copilot API"
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]

    database_url: str = f"sqlite:///{DB_PATH}"

    public_demo_mode: bool = False
    allow_custom_uploads: bool = True

    allow_external_queries: bool = True
    paperclip_api_key: str | None = None
    paperclip_base_url: str = "https://api.paperclip.gxl.ai"
    clinicaltrials_base_url: str = "https://clinicaltrials.gov/api/v2"

    llm_provider: Literal["auto", "hosted", "ollama", "none"] = "auto"
    hosted_llm_base_url: str | None = None
    hosted_llm_api_key: str | None = None
    hosted_llm_model: str = "gpt-4.1-mini"
    hosted_llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 700

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    ollama_enabled: bool = True
    ollama_timeout_seconds: float = 30.0

    session_secret: str = "dev-only-change-in-production"
    session_cookie_name: str = "mofa_demo_session"
    session_ttl_hours: int = 24
    run_retention_hours: int = 24
    rate_limit_per_minute: int = 30
    analysis_rate_limit_per_hour: int = 12

    external_query_cache_ttl_hours: int = 24
    disable_api_docs: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
