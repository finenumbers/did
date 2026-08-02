"""Add finenumbers provider_code; allow catalog without raw source id

Revision ID: 0009_finenumbers
Revises: 0008_abc_local
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_finenumbers"
down_revision: Union[str, None] = "0008_abc_local"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_code ADD VALUE 'finenumbers'")
    op.alter_column(
        "numbers_catalog_normalized",
        "raw_source_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "numbers_catalog_normalized",
        "raw_source_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    # PostgreSQL cannot easily remove enum values
