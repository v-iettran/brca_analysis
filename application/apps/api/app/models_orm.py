"""SQLite audit store: immutable analysis runs, warnings, external-query
caches, and export records. This is the only persistent state the API keeps;
everything scientific is recomputed deterministically from ``pipeline_core``
and the versioned artifact CSVs on every run.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class AnalysisRun(Base):
    """One immutable, reproducible analysis of a single patient profile."""

    __tablename__ = "analysis_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|completed|failed
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_label: Mapped[str] = mapped_column(String)  # de-identified label only
    patient_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    administered_regimen: Mapped[list] = mapped_column(JSON, default=list)
    expression_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signature_top_up: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signature_top_down: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    classifier_method: Mapped[str | None] = mapped_column(String, nullable=True)
    classifier_version: Mapped[str | None] = mapped_column(String, nullable=True)
    cluster_probabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_level: Mapped[str | None] = mapped_column(String, nullable=True)
    gene_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    warnings: Mapped[list["RunWarning"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    exports: Mapped[list["ExportRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    stages: Mapped[list["AnalysisStage"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AnalysisStage(Base):
    __tablename__ = "analysis_stages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id"))
    stage_id: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="running")  # running|completed|failed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AnalysisRun] = relationship(back_populates="stages")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id"))
    role: Mapped[str] = mapped_column(String)  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    active_view: Mapped[str | None] = mapped_column(String, nullable=True)
    used_local_model: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rationale: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AnalysisRun] = relationship(back_populates="chat_messages")


class RunWarning(Base):
    __tablename__ = "run_warnings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id"))
    severity: Mapped[str] = mapped_column(String, default="info")  # info|caution|abstain
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AnalysisRun] = relationship(back_populates="warnings")


class AuditEvent(Base):
    """Full technical trail: every tool call, its inputs (no secrets), and
    timing, so the technical view can reconstruct exactly what happened."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id"))
    tool_name: Mapped[str] = mapped_column(String)
    input_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AnalysisRun] = relationship(back_populates="audit_events")


class ExternalQueryCache(Base):
    """Cache of external Paperclip/ClinicalTrials.gov responses, keyed by a
    stable hash of (service, query). Never stores patient identifiers."""

    __tablename__ = "external_query_cache"

    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    service: Mapped[str] = mapped_column(String)  # "paperclip" | "clinicaltrials"
    query_text: Mapped[str] = mapped_column(Text)
    response_json: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExportRecord(Base):
    __tablename__ = "export_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.run_id"))
    export_format: Mapped[str] = mapped_column(String)  # pdf|json|csv
    file_path: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped[AnalysisRun] = relationship(back_populates="exports")
