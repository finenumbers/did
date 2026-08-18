"""Local regions directory table (SipOut load button)

Revision ID: 0021_regions_directory
Revises: 0020_rtu_connected
Create Date: 2026-08-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_regions_directory"
down_revision: Union[str, None] = "0020_rtu_connected"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "regions_directory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("abc", sa.Text(), nullable=True),
        sa.Column("city_name", sa.Text(), nullable=False),
        sa.Column("region_name", sa.Text(), nullable=True),
        sa.Column("city_external_id", sa.Text(), nullable=True),
        sa.Column("region_external_id", sa.Text(), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_regions_directory_region_city",
        "regions_directory",
        ["region_name", "city_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_regions_directory_region_city", table_name="regions_directory")
    op.drop_table("regions_directory")
