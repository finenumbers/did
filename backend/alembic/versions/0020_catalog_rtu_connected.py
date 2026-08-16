"""Add rtu_connected to numbers_catalog_normalized

Revision ID: 0020_rtu_connected
Revises: 0019_mcn
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_rtu_connected"
down_revision: Union[str, None] = "0019_mcn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("rtu_connected", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("numbers_catalog_normalized", "rtu_connected")
