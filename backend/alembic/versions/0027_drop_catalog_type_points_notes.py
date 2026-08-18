"""Drop catalog type/points/notes/class/confidence and matching raw typed cols

Revision ID: 0027_drop_catalog_type_cols
Revises: 0026_regions_abc_unique
Create Date: 2026-08-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_drop_catalog_type_cols"
down_revision: Union[str, None] = "0026_regions_abc_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATALOG_INDEXES = (
    "ix_catalog_kind_present_number_type",
    "ix_catalog_kind_present_class",
)

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
    for name in _CATALOG_INDEXES:
        op.drop_index(name, table_name="numbers_catalog_normalized")
    op.drop_column("numbers_catalog_normalized", "number_type")
    op.drop_column("numbers_catalog_normalized", "points")
    op.drop_column("numbers_catalog_normalized", "notes")
    op.drop_column("numbers_catalog_normalized", "class")
    op.drop_column("numbers_catalog_normalized", "mapping_confidence")

    op.drop_column("aurora_free_numbers_raw", "number_type")
    for table in ("uis_free_numbers_raw", "uis_purchased_numbers_raw"):
        op.drop_column(table, "category")
    op.drop_column("uis_purchased_numbers_raw", "comment")
    op.drop_column("uis_purchased_numbers_raw", "name")
    for table in (
        "exolve_free_numbers_raw",
        "voximplant_free_numbers_raw",
        "mcn_free_numbers_raw",
    ):
        op.drop_column(table, "type_name")
        op.drop_column(table, "category_name")
    for col in ("user_comment", "order_id", "doc_status", "has_sms", "sign"):
        op.drop_column("sipout_purchased_numbers_raw", col)

    for stg in _STG_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {stg}")


def downgrade() -> None:
    mapping_confidence = postgresql.ENUM(
        "low", "medium", "high", name="mapping_confidence", create_type=False
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column(
            "mapping_confidence",
            mapping_confidence,
            nullable=False,
            server_default="low",
        ),
    )
    op.add_column("numbers_catalog_normalized", sa.Column("class", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("points", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "numbers_catalog_normalized", sa.Column("number_type", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_catalog_kind_present_class",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "class"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_number_type",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "number_type"],
        unique=False,
    )

    op.add_column("aurora_free_numbers_raw", sa.Column("number_type", sa.Text(), nullable=True))
    for table in ("uis_free_numbers_raw", "uis_purchased_numbers_raw"):
        op.add_column(table, sa.Column("category", sa.Text(), nullable=True))
    op.add_column("uis_purchased_numbers_raw", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("uis_purchased_numbers_raw", sa.Column("name", sa.Text(), nullable=True))
    for table in (
        "exolve_free_numbers_raw",
        "voximplant_free_numbers_raw",
        "mcn_free_numbers_raw",
    ):
        op.add_column(table, sa.Column("type_name", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("category_name", sa.Text(), nullable=True))
    for col in ("user_comment", "order_id", "doc_status", "has_sms", "sign"):
        op.add_column("sipout_purchased_numbers_raw", sa.Column(col, sa.Text(), nullable=True))
