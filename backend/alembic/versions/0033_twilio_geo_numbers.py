"""Twilio geo dictionary + available numbers snapshot

Revision ID: 0033_twilio_geo_numbers
Revises: 0032_twilio
Create Date: 2026-08-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_twilio_geo_numbers"
down_revision: Union[str, None] = "0032_twilio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "twilio_catalog",
        sa.Column("region_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "twilio_catalog",
        sa.Column("city_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "twilio_geo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id"),
            nullable=False,
        ),
        sa.Column("country_iso", sa.Text(), nullable=False),
        sa.Column("number_type", sa.Text(), nullable=False),
        sa.Column("region_filter", sa.Text(), nullable=False, server_default=""),
        sa.Column("region", sa.Text()),
        sa.Column("locality", sa.Text()),
        sa.Column("locality_norm", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "last_sync_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sync_jobs.id"),
        ),
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
        sa.UniqueConstraint(
            "provider_id",
            "country_iso",
            "number_type",
            "region_filter",
            "locality_norm",
            name="uq_twilio_geo_cell",
        ),
    )
    op.create_index("ix_twilio_geo_provider_id", "twilio_geo", ["provider_id"])
    op.create_index("ix_twilio_geo_country_iso", "twilio_geo", ["country_iso"])

    op.create_table(
        "twilio_available_numbers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.Text(), nullable=False),
        sa.Column("country_iso", sa.Text()),
        sa.Column("country_name", sa.Text()),
        sa.Column("number_type", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("locality", sa.Text()),
        sa.Column("address_requirements", sa.Text()),
        sa.Column("voice", sa.Boolean()),
        sa.Column("sms", sa.Boolean()),
        sa.Column("mms", sa.Boolean()),
        sa.Column("fax", sa.Boolean()),
        sa.Column("source", sa.Text(), nullable=False, server_default="geo_sync"),
        sa.Column(
            "last_sync_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sync_jobs.id"),
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("provider_id", "phone_number", name="uq_twilio_available_number"),
    )
    op.create_index("ix_twilio_available_numbers_provider_id", "twilio_available_numbers", ["provider_id"])
    op.create_index("ix_twilio_available_numbers_country_iso", "twilio_available_numbers", ["country_iso"])
    op.create_index("ix_twilio_available_numbers_country_name", "twilio_available_numbers", ["country_name"])
    op.create_index("ix_twilio_available_numbers_number_type", "twilio_available_numbers", ["number_type"])
    op.create_index("ix_twilio_available_numbers_region", "twilio_available_numbers", ["region"])
    op.create_index("ix_twilio_available_numbers_locality", "twilio_available_numbers", ["locality"])


def downgrade() -> None:
    op.drop_index("ix_twilio_available_numbers_locality", table_name="twilio_available_numbers")
    op.drop_index("ix_twilio_available_numbers_region", table_name="twilio_available_numbers")
    op.drop_index("ix_twilio_available_numbers_number_type", table_name="twilio_available_numbers")
    op.drop_index("ix_twilio_available_numbers_country_name", table_name="twilio_available_numbers")
    op.drop_index("ix_twilio_available_numbers_country_iso", table_name="twilio_available_numbers")
    op.drop_index("ix_twilio_available_numbers_provider_id", table_name="twilio_available_numbers")
    op.drop_table("twilio_available_numbers")
    op.drop_index("ix_twilio_geo_country_iso", table_name="twilio_geo")
    op.drop_index("ix_twilio_geo_provider_id", table_name="twilio_geo")
    op.drop_table("twilio_geo")
    op.drop_column("twilio_catalog", "city_count")
    op.drop_column("twilio_catalog", "region_count")
