"""TTL cleanup for demo analysis runs and chat."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal
from app.models_orm import AnalysisRun, AnalysisStage, AuditEvent, ChatMessage, ExportRecord, RunWarning


def purge_expired_runs() -> int:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=get_settings().run_retention_hours)
    db = SessionLocal()
    try:
        expired_ids = [
            row[0]
            for row in db.query(AnalysisRun.run_id).filter(AnalysisRun.created_at < cutoff).all()
        ]
        if not expired_ids:
            return 0
        for model in (ChatMessage, AuditEvent, RunWarning, AnalysisStage, ExportRecord):
            db.execute(delete(model).where(model.run_id.in_(expired_ids)))
        db.execute(delete(AnalysisRun).where(AnalysisRun.run_id.in_(expired_ids)))
        db.commit()
        return len(expired_ids)
    finally:
        db.close()
