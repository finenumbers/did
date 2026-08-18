"""Add gar_territory to pstn_inn_ranges_cache

Revision ID: 0022_pstn_gar_territory
Revises: 0021_regions_directory
Create Date: 2026-08-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_pstn_gar_territory"
down_revision: Union[str, None] = "0021_regions_directory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pstn_inn_ranges_cache", sa.Column("gar_territory", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pstn_inn_ranges_cache", "gar_territory")
