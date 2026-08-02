"""catalog abc_code + number_local

Revision ID: 0008_abc_local
Revises: 0007_facet_indexes
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_abc_local"
down_revision: Union[str, None] = "0007_facet_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("numbers_catalog_normalized", sa.Column("abc_code", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("number_local", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE numbers_catalog_normalized
        SET
          abc_code = SUBSTRING(msisdn FROM 2 FOR 3),
          number_local = SUBSTRING(msisdn FROM 5)
        WHERE msisdn ~ '^7[0-9]{10}$'
        """
    )
    op.create_index(
        "ix_catalog_kind_present_abc",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "abc_code"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_number_local",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "number_local"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_kind_present_number_local", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_abc", table_name="numbers_catalog_normalized")
    op.drop_column("numbers_catalog_normalized", "number_local")
    op.drop_column("numbers_catalog_normalized", "abc_code")
