"""Add novofon provider_code and Novofon raw number tables

Revision ID: 0042_provider_novofon
Revises: 0041_aurora_fee_buy_price
Create Date: 2026-11-05

The new enum value is not inserted into providers in this transaction.
seed_providers() creates the row after migrate.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_provider_novofon"
down_revision: Union[str, None] = "0041_aurora_fee_buy_price"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE IF NOT EXISTS 'novofon'")

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
        "novofon_free_numbers_raw",
        [
            sa.Column("phone", sa.Text()),
            sa.Column("location_name", sa.Text()),
            sa.Column("location_mnemonic", sa.Text()),
        ],
    )
    op.create_index("ix_novofon_free_numbers_raw_phone", "novofon_free_numbers_raw", ["phone"])

    raw_table(
        "novofon_purchased_numbers_raw",
        [
            sa.Column("phone", sa.Text()),
            sa.Column("external_id", sa.Text()),
            sa.Column("status", sa.Text()),
        ],
    )
    op.create_index(
        "ix_novofon_purchased_numbers_raw_phone",
        "novofon_purchased_numbers_raw",
        ["phone"],
    )
    op.create_index(
        "ix_novofon_purchased_numbers_raw_external_id",
        "novofon_purchased_numbers_raw",
        ["external_id"],
    )


def downgrade() -> None:
    op.drop_table("novofon_purchased_numbers_raw")
    op.drop_table("novofon_free_numbers_raw")
    # PostgreSQL cannot easily remove enum values
