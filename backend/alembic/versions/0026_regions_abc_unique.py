"""Regions directory: unique ABC, drop city+region uniqueness

Revision ID: 0026_regions_abc_unique
Revises: 0025_regions_digit_capacity
Create Date: 2026-08-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_regions_abc_unique"
down_revision: Union[str, None] = "0025_regions_digit_capacity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE regions_directory")
    op.execute("DROP INDEX IF EXISTS uq_regions_directory_city_region")
    op.add_column("regions_directory", sa.Column("abc", sa.Text(), nullable=False))
    op.create_index("uq_regions_directory_abc", "regions_directory", ["abc"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_regions_directory_abc", table_name="regions_directory")
    op.drop_column("regions_directory", "abc")
    op.execute(
        "CREATE UNIQUE INDEX uq_regions_directory_city_region "
        "ON regions_directory (city_name, COALESCE(region_name, ''))"
    )
