"""Regions directory: persist editable digit capacity

Revision ID: 0025_regions_digit_capacity
Revises: 0024_regions_from_catalog
Create Date: 2026-08-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_regions_digit_capacity"
down_revision: Union[str, None] = "0024_regions_from_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "regions_directory",
        sa.Column("digit_capacity", sa.Integer(), nullable=False, server_default="7"),
    )
    op.alter_column("regions_directory", "digit_capacity", server_default=None)


def downgrade() -> None:
    op.drop_column("regions_directory", "digit_capacity")
