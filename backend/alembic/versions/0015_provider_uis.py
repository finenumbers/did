"""Add uis provider_code and UIS raw number tables

Revision ID: 0015_uis
Revises: 0014_purge_runexis_non_free
Create Date: 2026-08-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_uis"
down_revision: Union[str, None] = "0014_purge_runexis_non_free"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE 'uis'")

    def raw_table(name: str, extra_cols: list) -> None:
        cols = [
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
            *extra_cols,
        ]
        op.create_table(name, *cols)
        op.create_index(f"ix_{name}_sync_job_id", name, ["sync_job_id"])
        op.create_index(f"ix_{name}_external_key", name, ["external_key"])

    raw_table(
        "uis_free_numbers_raw",
        [
            sa.Column("phone", sa.Text()),
            sa.Column("category", sa.Text()),
            sa.Column("location_name", sa.Text()),
            sa.Column("location_mnemonic", sa.Text()),
        ],
    )
    op.create_index("ix_uis_free_numbers_raw_phone", "uis_free_numbers_raw", ["phone"])

    raw_table(
        "uis_purchased_numbers_raw",
        [
            sa.Column("phone", sa.Text()),
            sa.Column("external_id", sa.Text()),
            sa.Column("status", sa.Text()),
            sa.Column("category", sa.Text()),
            sa.Column("name", sa.Text()),
            sa.Column("comment", sa.Text()),
        ],
    )
    op.create_index("ix_uis_purchased_numbers_raw_phone", "uis_purchased_numbers_raw", ["phone"])
    op.create_index(
        "ix_uis_purchased_numbers_raw_external_id",
        "uis_purchased_numbers_raw",
        ["external_id"],
    )


def downgrade() -> None:
    op.drop_table("uis_purchased_numbers_raw")
    op.drop_table("uis_free_numbers_raw")
    # PostgreSQL cannot easily remove enum values
