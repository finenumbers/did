"""Add mcn provider_code and MCN raw tables

Revision ID: 0019_mcn
Revises: 0018_voximplant
Create Date: 2026-08-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_mcn"
down_revision: Union[str, None] = "0018_voximplant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE 'mcn'")

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
        "mcn_regions_raw",
        [
            sa.Column("region_external_id", sa.Text()),
            sa.Column("name", sa.Text()),
            sa.Column("eng_name", sa.Text()),
            sa.Column("parent_region_id", sa.Text()),
            sa.Column("region_code", sa.Text()),
        ],
    )
    raw_table(
        "mcn_cities_raw",
        [
            sa.Column("city_external_id", sa.Text()),
            sa.Column("city_name", sa.Text()),
            sa.Column("eng_name", sa.Text()),
            sa.Column("region_external_id", sa.Text()),
            sa.Column("region_name", sa.Text()),
            sa.Column("free_numbers_count", sa.Integer()),
        ],
    )
    raw_table(
        "mcn_free_numbers_raw",
        [
            sa.Column("phone", sa.Text()),
            sa.Column("type_name", sa.Text()),
            sa.Column("category_name", sa.Text()),
            sa.Column("region_name", sa.Text()),
            sa.Column("install_fee", sa.Numeric(18, 4)),
            sa.Column("subscription_fee", sa.Numeric(18, 4)),
        ],
    )
    op.create_index(
        "ix_mcn_free_numbers_raw_phone", "mcn_free_numbers_raw", ["phone"]
    )


def downgrade() -> None:
    op.drop_index("ix_mcn_free_numbers_raw_phone", table_name="mcn_free_numbers_raw")
    op.drop_table("mcn_free_numbers_raw")
    op.drop_table("mcn_cities_raw")
    op.drop_table("mcn_regions_raw")
