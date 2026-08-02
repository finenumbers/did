"""drop unused catalog columns

Revision ID: 0004_drop_catalog_cols
Revises: 0003_runexis_extra
Create Date: 2026-08-02

Remove has_sms, tariff_name, price_currency, status_normalized from
numbers_catalog_normalized. Provider values for these stay in raw tables / raw_payload.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_drop_catalog_cols"
down_revision: Union[str, None] = "0003_runexis_extra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("numbers_catalog_normalized", "has_sms")
    op.drop_column("numbers_catalog_normalized", "tariff_name")
    op.drop_column("numbers_catalog_normalized", "price_currency")
    op.drop_column("numbers_catalog_normalized", "status_normalized")


def downgrade() -> None:
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("status_normalized", sa.Text(), nullable=True),
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("price_currency", sa.Text(), nullable=True),
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("tariff_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("has_sms", sa.Boolean(), nullable=True),
    )
