"""Anonymous signed demo-session cookies."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models_orm import AnalysisRun


def _settings():
    return get_settings()


def _sign(session_id: str) -> str:
    digest = hmac.new(
        _settings().session_secret.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{session_id}.{digest}"


def parse_session_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    session_id, signature = token.rsplit(".", 1)
    expected = hmac.new(
        _settings().session_secret.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return session_id


def new_session_token() -> tuple[str, str]:
    session_id = secrets.token_urlsafe(24)
    return session_id, _sign(session_id)


def attach_session_cookie(response: Response, token: str) -> None:
    settings = _settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def get_or_create_session(request: Request, response: Response) -> str:
    session_id = parse_session_token(request.cookies.get(_settings().session_cookie_name))
    if session_id:
        request.state.session_id = session_id
        return session_id
    session_id, token = new_session_token()
    attach_session_cookie(response, token)
    request.state.session_id = session_id
    return session_id


def optional_session_id(request: Request) -> str | None:
    token = request.cookies.get(_settings().session_cookie_name)
    return parse_session_token(token)


def require_run_session(run_session_id: str | None, request: Request) -> None:
    """In public demo mode, a run may only be read by the creating session."""
    if not _settings().public_demo_mode:
        return
    current = optional_session_id(request) or getattr(request.state, "session_id", None)
    if not run_session_id or not current or run_session_id != current:
        raise HTTPException(status_code=404, detail="Unknown run_id")


def get_owned_run(db: Session, run_id: str, request: Request) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run_id {run_id!r}")
    require_run_session(run.session_id, request)
    return run
