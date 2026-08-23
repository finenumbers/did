"""Add didww provider_code, sync_job_type and DIDWW tables

Revision ID: 0031_didww
Revises: 0030_drop_mask_period
Create Date: 2026-08-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_didww"
down_revision: Union[str, None] = "0030_drop_mask_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE IF NOT EXISTS 'didww'")
    op.execute("ALTER TYPE sync_job_type ADD VALUE IF NOT EXISTS 'didww'")

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
        "didww_countries_raw",
        [
            sa.Column("name", sa.Text()),
            sa.Column("iso", sa.Text()),
            sa.Column("prefix", sa.Text()),
        ],
    )
    raw_table(
        "didww_regions_raw",
        [
            sa.Column("name", sa.Text()),
            sa.Column("country_external_id", sa.Text()),
            sa.Column("iso", sa.Text()),
        ],
    )
    raw_table(
        "didww_cities_raw",
        [
            sa.Column("name", sa.Text()),
            sa.Column("country_external_id", sa.Text()),
            sa.Column("region_external_id", sa.Text()),
        ],
    )
    raw_table(
        "didww_did_group_types_raw",
        [sa.Column("name", sa.Text())],
    )
    raw_table(
        "didww_did_groups_raw",
        [
            sa.Column("prefix", sa.Text()),
            sa.Column("area_name", sa.Text()),
            sa.Column("country_iso", sa.Text()),
        ],
    )

    op.create_table(
        "didww_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id"),
            nullable=False,
        ),
        sa.Column("provider_group_key", sa.Text(), nullable=False),
        sa.Column("country_name", sa.Text()),
        sa.Column("country_iso", sa.Text()),
        sa.Column("country_prefix", sa.Text()),
        sa.Column("region_name", sa.Text()),
        sa.Column("city_name", sa.Text()),
        sa.Column("area_prefix", sa.Text()),
        sa.Column("did_type", sa.Text()),
        sa.Column("buy_price", sa.Numeric(18, 4)),
        sa.Column("period_price", sa.Numeric(18, 4)),
        sa.Column("channels_included", sa.Integer()),
        sa.Column("stock_count", sa.Integer()),
        sa.Column("number_select", sa.Boolean()),
        sa.Column("features", sa.Text()),
        sa.Column("needs_registration", sa.Boolean()),
        sa.Column("is_metered", sa.Boolean()),
        sa.Column("skus_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "field_verification",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("raw_source_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "last_sync_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sync_jobs.id"),
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_currently_present", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("provider_id", "provider_group_key", name="uq_didww_catalog_provider_group"),
    )
    op.create_index("ix_didww_catalog_provider_id", "didww_catalog", ["provider_id"])
    op.create_index("ix_didww_catalog_country_name", "didww_catalog", ["country_name"])
    op.create_index("ix_didww_catalog_country_iso", "didww_catalog", ["country_iso"])
    op.create_index("ix_didww_catalog_area_prefix", "didww_catalog", ["area_prefix"])
    op.create_index("ix_didww_catalog_did_type", "didww_catalog", ["did_type"])


def downgrade() -> None:
    op.drop_index("ix_didww_catalog_did_type", table_name="didww_catalog")
    op.drop_index("ix_didww_catalog_area_prefix", table_name="didww_catalog")
    op.drop_index("ix_didww_catalog_country_iso", table_name="didww_catalog")
    op.drop_index("ix_didww_catalog_country_name", table_name="didww_catalog")
    op.drop_index("ix_didww_catalog_provider_id", table_name="didww_catalog")
    op.drop_table("didww_catalog")
    for name in (
        "didww_did_groups_raw",
        "didww_did_group_types_raw",
        "didww_cities_raw",
        "didww_regions_raw",
        "didww_countries_raw",
    ):
        op.drop_index(f"ix_{name}_external_key", table_name=name)
        op.drop_index(f"ix_{name}_sync_job_id", table_name=name)
        op.drop_table(name)
