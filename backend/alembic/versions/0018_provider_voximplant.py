"""Add voximplant provider_code and Voximplant raw tables

Revision ID: 0018_voximplant
Revises: 0017_exolve
Create Date: 2026-08-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_voximplant"
down_revision: Union[str, None] = "0017_exolve"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE 'voximplant'")

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
        "voximplant_regions_raw",
        [
            sa.Column("region_external_id", sa.Text()),
            sa.Column("name", sa.Text()),
            sa.Column("eng_name", sa.Text()),
            sa.Column("parent_region_id", sa.Text()),
            sa.Column("region_code", sa.Text()),
            sa.Column("category_name", sa.Text()),
            sa.Column("phone_count", sa.Integer()),
            sa.Column("phone_price", sa.Numeric(18, 4)),
            sa.Column("phone_installation_price", sa.Numeric(18, 4)),
        ],
    )
    raw_table(
        "voximplant_cities_raw",
        [
            sa.Column("city_external_id", sa.Text()),
            sa.Column("city_name", sa.Text()),
            sa.Column("eng_name", sa.Text()),
            sa.Column("region_external_id", sa.Text()),
            sa.Column("region_name", sa.Text()),
        ],
    )
    raw_table(
        "voximplant_categories_raw",
        [
            sa.Column("category_external_id", sa.Text()),
            sa.Column("category_name", sa.Text()),
            sa.Column("type_id", sa.Text()),
            sa.Column("type_name", sa.Text()),
        ],
    )
    raw_table(
        "voximplant_free_numbers_raw",
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
        "ix_voximplant_free_numbers_raw_phone",
        "voximplant_free_numbers_raw",
        ["phone"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_voximplant_free_numbers_raw_phone",
        table_name="voximplant_free_numbers_raw",
    )
    op.drop_table("voximplant_free_numbers_raw")
    op.drop_table("voximplant_categories_raw")
    op.drop_table("voximplant_cities_raw")
    op.drop_table("voximplant_regions_raw")
