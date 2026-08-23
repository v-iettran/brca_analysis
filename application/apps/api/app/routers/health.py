from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.adapters.llm.factory import get_llm_client
from app.adapters.ollama_client import is_ollama_reachable
from app.config import get_settings
from app.db import SessionLocal
from app.services.demo_bundle import bundle_ready
from pipeline_core.compound_registry import load_registry, registry_version
from pipeline_core.config import COMPOUND_REGISTRY_MANIFEST, PUBLIC_DEMO_BUNDLE_DIR

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    db_ok = False
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception:
        db_ok = False

    registry = load_registry()
    client = get_llm_client()
    hosted_configured = bool(settings.hosted_llm_base_url and settings.hosted_llm_api_key)
    ollama_reachable = (
        is_ollama_reachable(settings.ollama_host) if settings.ollama_enabled else False
    )
    ready = db_ok and (not settings.public_demo_mode or bundle_ready())
    status = "ok" if ready else "degraded"
    return {
        "status": status,
        "app_name": settings.app_name,
        "environment": settings.environment,
        "public_demo_mode": settings.public_demo_mode,
        "allow_custom_uploads": settings.allow_custom_uploads and not settings.public_demo_mode,
        "database_ok": db_ok,
        "public_bundle_ready": bundle_ready(),
        "public_bundle_dir": str(PUBLIC_DEMO_BUNDLE_DIR),
        "compound_registry_version": registry_version(),
        "compound_registry_ready": COMPOUND_REGISTRY_MANIFEST.exists() or not registry.empty,
        "compound_registry_size": int(len(registry)),
        "llm_provider": settings.llm_provider,
        "llm_active_provider": client.provider_name,
        "llm_active_model": client.model_name,
        "hosted_llm_configured": hosted_configured,
        "ollama_enabled": settings.ollama_enabled,
        "ollama_reachable": ollama_reachable if settings.ollama_enabled else None,
        "external_queries_allowed": settings.allow_external_queries,
    }
