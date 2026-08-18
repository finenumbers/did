"""Regions directory: catalog snapshot, drop SipOut extras

Revision ID: 0024_regions_from_catalog
Revises: 0023_drop_catalog_fields
Create Date: 2026-08-18

Regions page stores distinct city/region pairs from the numbers catalog.
SipOut ids and unused abc are removed. Existing SipOut snapshot is cleared.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_regions_from_catalog"
down_revision: Union[str, None] = "0023_drop_catalog_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE regions_directory")
    op.drop_index("ix_regions_directory_region_city", table_name="regions_directory")
    op.drop_column("regions_directory", "abc")
    op.drop_column("regions_directory", "city_external_id")
    op.drop_column("regions_directory", "region_external_id")
    op.execute(
        "CREATE UNIQUE INDEX uq_regions_directory_city_region "
        "ON regions_directory (city_name, COALESCE(region_name, ''))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_regions_directory_city_region")
    op.add_column("regions_directory", sa.Column("abc", sa.Text(), nullable=True))
    op.add_column("regions_directory", sa.Column("city_external_id", sa.Text(), nullable=True))
    op.add_column("regions_directory", sa.Column("region_external_id", sa.Text(), nullable=True))
    op.create_index(
        "ix_regions_directory_region_city",
        "regions_directory",
        ["region_name", "city_name"],
    )
