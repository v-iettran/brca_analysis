"""Rate limit and retention helpers."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.middleware.rate_limit import enforce_rate_limit, reset_rate_limits
from app.models_orm import AnalysisRun
from app.db import SessionLocal
from app.services.retention_service import purge_expired_runs
from app.config import get_settings


def test_rate_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    get_settings.cache_clear()
    reset_rate_limits()
    request = SimpleNamespace(cookies={}, headers={}, client=SimpleNamespace(host="1.2.3.4"), state=SimpleNamespace())
    for _ in range(3):
        enforce_rate_limit(request, "unit", 3, 60)
    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(request, "unit", 3, 60)
    assert exc.value.status_code == 429
    reset_rate_limits()
    get_settings.cache_clear()


def test_purge_expired_runs_deletes_old_rows():
    db = SessionLocal()
    try:
        old = AnalysisRun(
            patient_label="old",
            patient_metadata={},
            administered_regimen=[],
            status="completed",
            created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=get_settings().run_retention_hours + 5),
        )
        fresh = AnalysisRun(
            patient_label="fresh",
            patient_metadata={},
            administered_regimen=[],
            status="completed",
        )
        db.add_all([old, fresh])
        db.commit()
        old_id, fresh_id = old.run_id, fresh.run_id
    finally:
        db.close()
    deleted = purge_expired_runs()
    assert deleted >= 1
    db = SessionLocal()
    try:
        assert db.get(AnalysisRun, old_id) is None
        assert db.get(AnalysisRun, fresh_id) is not None
    finally:
        db.close()
