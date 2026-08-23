from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models_orm  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()


def _sqlite_add_missing_columns() -> None:
    """Additive SQLite migration for V2 columns (create_all does not alter)."""
    if not settings.database_url.startswith("sqlite"):
        return
    statements = [
        "ALTER TABLE analysis_runs ADD COLUMN expression_snapshot JSON",
        "ALTER TABLE analysis_runs ADD COLUMN signature_top_up INTEGER",
        "ALTER TABLE analysis_runs ADD COLUMN signature_top_down INTEGER",
        "ALTER TABLE analysis_runs ADD COLUMN revision INTEGER DEFAULT 0",
        "ALTER TABLE analysis_runs ADD COLUMN current_stage VARCHAR",
        "ALTER TABLE analysis_runs ADD COLUMN session_id VARCHAR",
        "ALTER TABLE chat_messages ADD COLUMN rationale JSON",
        "ALTER TABLE chat_messages ADD COLUMN llm_provider VARCHAR",
        "ALTER TABLE chat_messages ADD COLUMN llm_model VARCHAR",
    ]
    with engine.begin() as conn:
        for sql in statements:
            try:
                conn.exec_driver_sql(sql)
            except Exception:
                # Column already exists.
                pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
