"""sync_runs + sync_run_logs for unified sync

Revision ID: 0010_sync_runs
Revises: 0009_finenumbers
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_sync_runs"
down_revision: Union[str, None] = "0009_finenumbers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

sync_job_status = postgresql.ENUM(
    "pending",
    "running",
    "success",
    "failed",
    "partial",
    name="sync_job_status",
    create_type=False,
)
sync_log_level = postgresql.ENUM(
    "debug",
    "info",
    "warning",
    "error",
    name="sync_log_level",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sync_job_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_sync_runs_created_at", "sync_runs", ["created_at"])
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])

    op.create_table(
        "sync_run_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sync_log_level, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sync_run_logs_sync_run_id", "sync_run_logs", ["sync_run_id"])
    op.create_index("ix_sync_run_logs_created_at", "sync_run_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_run_logs_created_at", table_name="sync_run_logs")
    op.drop_index("ix_sync_run_logs_sync_run_id", table_name="sync_run_logs")
    op.drop_table("sync_run_logs")
    op.drop_index("ix_sync_runs_status", table_name="sync_runs")
    op.drop_index("ix_sync_runs_created_at", table_name="sync_runs")
    op.drop_table("sync_runs")
