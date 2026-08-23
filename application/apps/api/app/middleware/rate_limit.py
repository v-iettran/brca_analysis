"""In-process rate limiter for the public demo."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings
from app.services.session_service import optional_session_id

_HITS: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    session_id = optional_session_id(request)
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    host = forwarded or (request.client.host if request.client else "unknown")
    return session_id or host


def enforce_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    key = f"{bucket}:{_client_key(request)}"
    now = time.time()
    hits = _HITS[key]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    hits.append(now)


def limit_general(request: Request) -> None:
    if not get_settings().public_demo_mode:
        return
    enforce_rate_limit(request, "general", get_settings().rate_limit_per_minute, 60)


def limit_analysis(request: Request) -> None:
    if not get_settings().public_demo_mode:
        return
    enforce_rate_limit(request, "analysis", get_settings().analysis_rate_limit_per_hour, 3600)


def limit_llm(request: Request) -> None:
    if not get_settings().public_demo_mode:
        return
    enforce_rate_limit(request, "llm", min(get_settings().rate_limit_per_minute, 20), 60)


def reset_rate_limits() -> None:
    _HITS.clear()
