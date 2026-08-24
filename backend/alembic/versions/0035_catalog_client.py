"""Add client (REG Описание) to numbers_catalog_normalized

Revision ID: 0035_catalog_client
Revises: 0034_twilio_numbers_sync
Create Date: 2026-08-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_catalog_client"
down_revision: Union[str, None] = "0034_twilio_numbers_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("client", sa.Text(), nullable=True),
    )
    op.execute("DROP TABLE IF EXISTS numbers_catalog_normalized_stg")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS numbers_catalog_normalized_stg")
    op.drop_column("numbers_catalog_normalized", "client")
