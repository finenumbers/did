"""Drop catalog mask/display_mask; add type_label/premium; create mask_types

Revision ID: 0028_mask_types
Revises: 0027_drop_catalog_type_cols
Create Date: 2026-08-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_mask_types"
down_revision: Union[str, None] = "0027_drop_catalog_type_cols"
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


def upgrade() -> None:
    op.drop_index("ix_catalog_kind_present_mask", table_name="numbers_catalog_normalized")
    op.drop_column("numbers_catalog_normalized", "mask")
    op.drop_column("numbers_catalog_normalized", "display_mask")
    op.add_column(
        "numbers_catalog_normalized", sa.Column("type_label", sa.Text(), nullable=True)
    )
    op.add_column(
        "numbers_catalog_normalized", sa.Column("premium", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_catalog_kind_present_type_label",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "type_label"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_premium",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "premium"],
        unique=False,
    )
    op.create_table(
        "mask_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("digit_capacity", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("abc", sa.Text(), nullable=False, server_default=""),
        sa.Column("mask", sa.Text(), nullable=False),
        sa.Column("type_label", sa.Text(), nullable=True),
        sa.Column("premium", sa.Text(), nullable=True),
        sa.Column("purchase", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "digit_capacity",
            "category",
            "abc",
            "mask",
            name="uq_mask_types_key",
        ),
    )
    for stg in _STG_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {stg}")


def downgrade() -> None:
    op.drop_table("mask_types")
    op.drop_index("ix_catalog_kind_present_premium", table_name="numbers_catalog_normalized")
    op.drop_index(
        "ix_catalog_kind_present_type_label", table_name="numbers_catalog_normalized"
    )
    op.drop_column("numbers_catalog_normalized", "premium")
    op.drop_column("numbers_catalog_normalized", "type_label")
    op.add_column(
        "numbers_catalog_normalized", sa.Column("display_mask", sa.Text(), nullable=True)
    )
    op.add_column(
        "numbers_catalog_normalized", sa.Column("mask", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_catalog_kind_present_mask",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "mask"],
        unique=False,
    )
