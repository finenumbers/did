"""Mask-type prices as numeric; catalog mask_purchase/mask_period

Revision ID: 0029_mask_type_prices
Revises: 0028_mask_types
Create Date: 2026-08-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_mask_type_prices"
down_revision: Union[str, None] = "0028_mask_types"
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
_USING = (
    "CASE "
    "WHEN {col} IS NULL THEN NULL "
    "WHEN BTRIM({col}::text) = '' THEN NULL "
    "WHEN BTRIM(REPLACE({col}::text, ',', '.')) ~ '^[+-]?[0-9]+(\\.[0-9]+)?$' "
    "THEN BTRIM(REPLACE({col}::text, ',', '.'))::numeric "
    "ELSE NULL END"
)


def upgrade() -> None:
    op.add_column("mask_types", sa.Column("period", _NUMERIC, nullable=True))
    op.execute(
        f"ALTER TABLE mask_types ALTER COLUMN premium TYPE NUMERIC(18, 4) USING {_USING.format(col='premium')}"
    )
    op.execute(
        f"ALTER TABLE mask_types ALTER COLUMN purchase TYPE NUMERIC(18, 4) USING {_USING.format(col='purchase')}"
    )

    op.drop_index("ix_catalog_kind_present_premium", table_name="numbers_catalog_normalized")
    op.execute(
        "ALTER TABLE numbers_catalog_normalized ALTER COLUMN premium "
        f"TYPE NUMERIC(18, 4) USING {_USING.format(col='premium')}"
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("mask_purchase", _NUMERIC, nullable=True),
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("mask_period", _NUMERIC, nullable=True),
    )
    op.create_index(
        "ix_catalog_kind_present_premium",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "premium"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_mask_purchase",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "mask_purchase"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_mask_period",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "mask_period"],
        unique=False,
    )
    for stg in _STG_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {stg}")


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_kind_present_mask_period", table_name="numbers_catalog_normalized"
    )
    op.drop_index(
        "ix_catalog_kind_present_mask_purchase", table_name="numbers_catalog_normalized"
    )
    op.drop_index("ix_catalog_kind_present_premium", table_name="numbers_catalog_normalized")
    op.drop_column("numbers_catalog_normalized", "mask_period")
    op.drop_column("numbers_catalog_normalized", "mask_purchase")
    op.execute(
        "ALTER TABLE numbers_catalog_normalized ALTER COLUMN premium TYPE TEXT "
        "USING CASE WHEN premium IS NULL THEN NULL ELSE premium::text END"
    )
    op.create_index(
        "ix_catalog_kind_present_premium",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "premium"],
        unique=False,
    )
    op.execute("ALTER TABLE mask_types ALTER COLUMN purchase TYPE TEXT USING purchase::text")
    op.execute("ALTER TABLE mask_types ALTER COLUMN premium TYPE TEXT USING premium::text")
    op.drop_column("mask_types", "period")
