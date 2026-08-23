"""Twilio per-row number enrichment job + catalog dates

Revision ID: 0034_twilio_numbers_sync
Revises: 0033_twilio_geo_numbers
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_twilio_numbers_sync"
down_revision: Union[str, None] = "0033_twilio_geo_numbers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sync_job_type ADD VALUE IF NOT EXISTS 'twilio_numbers'")
    op.add_column("twilio_catalog", sa.Column("numbers_synced_at", sa.DateTime(timezone=True)))
    op.add_column(
        "twilio_catalog",
        sa.Column("numbers_sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id")),
    )
    op.add_column(
        "twilio_catalog",
        sa.Column(
            "numbers_sync_geo_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sync_jobs.id"),
        ),
    )


def downgrade() -> None:
    op.drop_column("twilio_catalog", "numbers_sync_geo_job_id")
    op.drop_column("twilio_catalog", "numbers_sync_job_id")
    op.drop_column("twilio_catalog", "numbers_synced_at")
