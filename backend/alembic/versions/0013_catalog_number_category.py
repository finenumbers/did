"""Add number_category (Категория) to catalog + backfill

Revision ID: 0013_number_category
Revises: 0012_single_active_sync_run
Create Date: 2026-08-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_number_category"
down_revision: Union[str, None] = "0012_single_active_sync_run"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("number_category", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_catalog_kind_present_number_category",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "number_category"],
        unique=False,
    )
    # Staging tables created via CREATE … AS SELECT keep old column sets — drop them.
    op.execute("DROP TABLE IF EXISTS numbers_catalog_normalized_stg")
    op.execute("DROP TABLE IF EXISTS sipout_free_numbers_raw_stg")
    op.execute("DROP TABLE IF EXISTS sipout_purchased_numbers_raw_stg")
    op.execute("DROP TABLE IF EXISTS runexis_free_numbers_raw_stg")
    op.execute("DROP TABLE IF EXISTS runexis_purchased_numbers_raw_stg")

    op.execute(
        """
        UPDATE numbers_catalog_normalized SET number_category = CASE
          WHEN COALESCE(NULLIF(BTRIM(abc_code), ''), SUBSTRING(msisdn FROM 2 FOR 3))
               LIKE '9%' THEN 'Мобильный'
          WHEN COALESCE(NULLIF(BTRIM(abc_code), ''), SUBSTRING(msisdn FROM 2 FOR 3))
               = '800' THEN 'Бесплатный вызов'
          WHEN COALESCE(NULLIF(BTRIM(abc_code), ''), SUBSTRING(msisdn FROM 2 FOR 3))
               IS NOT NULL
               AND BTRIM(
                 COALESCE(NULLIF(BTRIM(abc_code), ''), SUBSTRING(msisdn FROM 2 FOR 3))
               ) <> '' THEN 'Городской'
          ELSE NULL
        END
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_kind_present_number_category",
        table_name="numbers_catalog_normalized",
    )
    op.drop_column("numbers_catalog_normalized", "number_category")
