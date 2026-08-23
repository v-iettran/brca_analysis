from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import analysis, drugs, export, health, insights, patients
from app.services.retention_service import purge_expired_runs

settings = get_settings()


def _retention_loop() -> None:
    while True:
        time.sleep(3600)
        try:
            purge_expired_runs()
        except Exception:
            continue


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    try:
        purge_expired_runs()
    except Exception:
        pass
    worker = threading.Thread(target=_retention_loop, daemon=True, name="run-retention")
    worker.start()
    yield


docs_url = None if settings.disable_api_docs or settings.public_demo_mode else "/docs"
redoc_url = None if settings.disable_api_docs or settings.public_demo_mode else "/redoc"

app = FastAPI(
    title=settings.app_name,
    description=(
        "Research prototype backend. Not a clinical decision-support device. "
        "Public demo mode accepts only curated synthetic patients and never persists RNA. "
        "The LLM may summarize validated run evidence; it never selects therapies."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=None if settings.disable_api_docs or settings.public_demo_mode else "/openapi.json",
)

if settings.environment == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(health.router)
app.include_router(patients.router)
app.include_router(analysis.router)
app.include_router(insights.router)
app.include_router(drugs.router)
app.include_router(export.router)
