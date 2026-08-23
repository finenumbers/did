"""Add twilio provider_code, sync_job_type and Twilio tables

Revision ID: 0032_twilio
Revises: 0031_didww
Create Date: 2026-08-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_twilio"
down_revision: Union[str, None] = "0031_didww"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE IF NOT EXISTS 'twilio'")
    op.execute("ALTER TYPE sync_job_type ADD VALUE IF NOT EXISTS 'twilio'")

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
        "twilio_countries_raw",
        [
            sa.Column("country_name", sa.Text()),
            sa.Column("country_iso", sa.Text()),
            sa.Column("country_beta", sa.Boolean()),
        ],
    )
    raw_table(
        "twilio_pricing_raw",
        [
            sa.Column("country_iso", sa.Text()),
            sa.Column("price_unit", sa.Text()),
        ],
    )

    op.create_table(
        "twilio_catalog",
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
        sa.Column("number_type", sa.Text()),
        sa.Column("period_price", sa.Numeric(18, 4)),
        sa.Column("price_unit", sa.Text()),
        sa.Column("country_beta", sa.Boolean()),
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
        sa.UniqueConstraint("provider_id", "provider_group_key", name="uq_twilio_catalog_provider_group"),
    )
    op.create_index("ix_twilio_catalog_provider_id", "twilio_catalog", ["provider_id"])
    op.create_index("ix_twilio_catalog_country_name", "twilio_catalog", ["country_name"])
    op.create_index("ix_twilio_catalog_country_iso", "twilio_catalog", ["country_iso"])
    op.create_index("ix_twilio_catalog_number_type", "twilio_catalog", ["number_type"])


def downgrade() -> None:
    op.drop_index("ix_twilio_catalog_number_type", table_name="twilio_catalog")
    op.drop_index("ix_twilio_catalog_country_iso", table_name="twilio_catalog")
    op.drop_index("ix_twilio_catalog_country_name", table_name="twilio_catalog")
    op.drop_index("ix_twilio_catalog_provider_id", table_name="twilio_catalog")
    op.drop_table("twilio_catalog")
    for name in ("twilio_pricing_raw", "twilio_countries_raw"):
        op.drop_index(f"ix_{name}_external_key", table_name=name)
        op.drop_index(f"ix_{name}_sync_job_id", table_name=name)
        op.drop_table(name)
