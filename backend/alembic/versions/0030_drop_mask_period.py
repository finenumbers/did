"""Drop unused mask directory period / catalog mask_period

Revision ID: 0030_drop_mask_period
Revises: 0029_mask_type_prices
Create Date: 2026-08-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_drop_mask_period"
down_revision: Union[str, None] = "0029_mask_type_prices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STG_TABLES = (
    "numbers_catalog_normalized_stg",
    "sipout_purchased_numbers_raw_stg",
    "uis_free_numbers_raw_stg",
    "uis_purchased_numbers_raw_stg",
    "aurora_free_numbers_raw_stg",
    "exolve_free_numbers_raw_stg",
    "voximplant_free_numbers_raw_stg",
    "mcn_free_numbers_raw_stg",
)

_NUMERIC = sa.Numeric(18, 4)


def upgrade() -> None:
    op.drop_index(
        "ix_catalog_kind_present_mask_period", table_name="numbers_catalog_normalized"
    )
    op.drop_column("numbers_catalog_normalized", "mask_period")
    op.drop_column("mask_types", "period")
    for stg in _STG_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {stg}")


def downgrade() -> None:
    op.add_column("mask_types", sa.Column("period", _NUMERIC, nullable=True))
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("mask_period", _NUMERIC, nullable=True),
    )
    op.create_index(
        "ix_catalog_kind_present_mask_period",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "mask_period"],
        unique=False,
    )
