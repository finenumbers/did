"""catalog Runexis free extra fields

Revision ID: 0003_runexis_extra
Revises: 0002_buy_period
Create Date: 2026-08-02

Add mask, number_type, points, date_from, operator_fas, operator_id,
last_operation_date, manager_id, notes, abcdef to numbers_catalog_normalized.
Backfill Runexis free from runexis_free_numbers_raw.raw_payload.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_runexis_extra"
down_revision: Union[str, None] = "0002_buy_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("numbers_catalog_normalized", sa.Column("mask", sa.Text(), nullable=True))
    op.add_column(
        "numbers_catalog_normalized", sa.Column("number_type", sa.Text(), nullable=True)
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("points", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column("numbers_catalog_normalized", sa.Column("date_from", sa.Text(), nullable=True))
    op.add_column(
        "numbers_catalog_normalized", sa.Column("operator_fas", sa.Text(), nullable=True)
    )
    op.add_column(
        "numbers_catalog_normalized", sa.Column("operator_id", sa.Text(), nullable=True)
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("last_operation_date", sa.Text(), nullable=True),
    )
    op.add_column(
        "numbers_catalog_normalized", sa.Column("manager_id", sa.Text(), nullable=True)
    )
    op.add_column("numbers_catalog_normalized", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("abcdef", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET
          mask = NULLIF(BTRIM(r.raw_payload->>'mask'), ''),
          number_type = NULLIF(BTRIM(r.raw_payload->>'number_type'), ''),
          points = NULLIF(BTRIM(r.raw_payload->>'points'), '')::numeric,
          date_from = NULLIF(BTRIM(r.raw_payload->>'date_from'), ''),
          operator_fas = NULLIF(BTRIM(r.raw_payload->>'operator_fas'), ''),
          operator_id = NULLIF(BTRIM(r.raw_payload->>'operator_id'), ''),
          last_operation_date = NULLIF(BTRIM(r.raw_payload->>'last_operation_date'), ''),
          manager_id = NULLIF(BTRIM(r.raw_payload->>'manager_id'), ''),
          notes = NULLIF(BTRIM(r.raw_payload->>'notes'), ''),
          abcdef = NULLIF(BTRIM(r.raw_payload->>'abcdef'), '')
        FROM runexis_free_numbers_raw AS r,
             providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'runexis'
          AND c.inventory_kind = 'free'
          AND c.raw_source_id = r.id
        """
    )


def downgrade() -> None:
    op.drop_column("numbers_catalog_normalized", "abcdef")
    op.drop_column("numbers_catalog_normalized", "notes")
    op.drop_column("numbers_catalog_normalized", "manager_id")
    op.drop_column("numbers_catalog_normalized", "last_operation_date")
    op.drop_column("numbers_catalog_normalized", "operator_id")
    op.drop_column("numbers_catalog_normalized", "operator_fas")
    op.drop_column("numbers_catalog_normalized", "date_from")
    op.drop_column("numbers_catalog_normalized", "points")
    op.drop_column("numbers_catalog_normalized", "number_type")
    op.drop_column("numbers_catalog_normalized", "mask")
