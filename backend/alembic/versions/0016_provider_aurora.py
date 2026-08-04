"""Add aurora provider_code and aurora free numbers raw table

Revision ID: 0016_aurora
Revises: 0015_uis
Create Date: 2026-08-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_aurora"
down_revision: Union[str, None] = "0015_uis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE 'aurora'")

    op.create_table(
        "aurora_free_numbers_raw",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sync_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sync_jobs.id"),
            nullable=False,
        ),
        sa.Column("source_loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=True),
        sa.Column("external_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("phone", sa.Text()),
        sa.Column("number_type", sa.Text()),
        sa.Column("period_price_raw", sa.Text()),
        sa.Column("region_raw", sa.Text()),
        sa.Column("city_name", sa.Text()),
        sa.Column("region_name", sa.Text()),
        sa.Column("display_mask", sa.Text()),
    )
    op.create_index(
        "ix_aurora_free_numbers_raw_sync_job_id",
        "aurora_free_numbers_raw",
        ["sync_job_id"],
    )
    op.create_index(
        "ix_aurora_free_numbers_raw_external_key",
        "aurora_free_numbers_raw",
        ["external_key"],
    )
    op.create_index(
        "ix_aurora_free_numbers_raw_phone",
        "aurora_free_numbers_raw",
        ["phone"],
    )


def downgrade() -> None:
    op.drop_table("aurora_free_numbers_raw")
    # PostgreSQL cannot easily remove enum values
