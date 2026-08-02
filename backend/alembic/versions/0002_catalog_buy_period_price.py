"""catalog buy_price + period_price

Revision ID: 0002_buy_period
Revises: 0001_initial
Create Date: 2026-08-02

Rename numbers_catalog_normalized.price_amount → buy_price,
add period_price, backfill free inventory from provider semantics:
- SipOut free: former price → period_price, buy_price cleared
- Runexis free: buy_price/period_price from raw_payload
- purchased: former price stays in buy_price
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_buy_period"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "numbers_catalog_normalized",
        "price_amount",
        new_column_name="buy_price",
        existing_type=sa.Numeric(18, 4),
        existing_nullable=True,
    )
    op.add_column(
        "numbers_catalog_normalized",
        sa.Column("period_price", sa.Numeric(18, 4), nullable=True),
    )

    # SipOut free: API price is period (абонентская), not purchase
    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET period_price = c.buy_price,
            buy_price = NULL
        FROM providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'sipout'
          AND c.inventory_kind = 'free'
        """
    )

    # Runexis free: reload both prices from Numbering raw payload
    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET buy_price = NULLIF(r.raw_payload->>'buy_price', '')::numeric,
            period_price = NULLIF(r.raw_payload->>'period_price', '')::numeric
        FROM runexis_free_numbers_raw AS r,
             providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'runexis'
          AND c.inventory_kind = 'free'
          AND c.raw_source_id = r.id
        """
    )


def downgrade() -> None:
    # Collapse period into buy for SipOut free before rename (best-effort)
    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET buy_price = COALESCE(c.buy_price, c.period_price)
        FROM providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'sipout'
          AND c.inventory_kind = 'free'
        """
    )
    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET buy_price = COALESCE(c.period_price, c.buy_price)
        FROM providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'runexis'
          AND c.inventory_kind = 'free'
        """
    )
    op.drop_column("numbers_catalog_normalized", "period_price")
    op.alter_column(
        "numbers_catalog_normalized",
        "buy_price",
        new_column_name="price_amount",
        existing_type=sa.Numeric(18, 4),
        existing_nullable=True,
    )
