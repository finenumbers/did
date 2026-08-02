"""Sync jobs, unified sync runs, and logs."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SyncJobStatus, SyncJobType, SyncLogLevel


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    job_type: Mapped[SyncJobType] = mapped_column(Enum(SyncJobType, name="sync_job_type"), nullable=False)
    status: Mapped[SyncJobStatus] = mapped_column(
        Enum(SyncJobStatus, name="sync_job_status"), nullable=False, default=SyncJobStatus.pending
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    logs: Mapped[list["SyncJobLog"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class SyncJobLog(Base):
    __tablename__ = "sync_job_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[SyncLogLevel] = mapped_column(Enum(SyncLogLevel, name="sync_log_level"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    job: Mapped[SyncJob] = relationship(back_populates="logs")


class SyncRun(Base):
    """Unified multi-provider sync run with stage progress."""

    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[SyncJobStatus] = mapped_column(
        Enum(SyncJobStatus, name="sync_job_status", create_constraint=False),
        nullable=False,
        default=SyncJobStatus.pending,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    logs: Mapped[list["SyncRunLog"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SyncRunLog(Base):
    __tablename__ = "sync_run_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[SyncLogLevel] = mapped_column(
        Enum(SyncLogLevel, name="sync_log_level", create_constraint=False), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    run: Mapped[SyncRun] = relationship(back_populates="logs")
