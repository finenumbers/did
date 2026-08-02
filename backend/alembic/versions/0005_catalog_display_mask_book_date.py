"""catalog display_mask + book_date

Revision ID: 0005_display_book
Revises: 0004_drop_catalog_cols
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_display_book"
down_revision: Union[str, None] = "0004_drop_catalog_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "numbers_catalog_normalized", sa.Column("display_mask", sa.Text(), nullable=True)
    )
    op.add_column(
        "numbers_catalog_normalized", sa.Column("book_date", sa.Text(), nullable=True)
    )
    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET
          display_mask = NULLIF(BTRIM(r.raw_payload->>'display_mask'), ''),
          book_date = CASE
            WHEN NULLIF(BTRIM(r.raw_payload->>'book_date'), '') IS NULL THEN NULL
            WHEN r.raw_payload->>'book_date' LIKE '0000%' THEN NULL
            ELSE BTRIM(r.raw_payload->>'book_date')
          END
        FROM runexis_free_numbers_raw AS r,
             providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'runexis'
          AND c.inventory_kind = 'free'
          AND c.raw_source_id = r.id
        """
    )


def downgrade() -> None:
    op.drop_column("numbers_catalog_normalized", "book_date")
    op.drop_column("numbers_catalog_normalized", "display_mask")
