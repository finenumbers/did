"""Move Aurora CSV fee from period_price to buy_price.

Revision ID: 0041_aurora_fee_buy_price
Revises: 0040_twilio_numbers_resume
Create Date: 2026-10-31

The file amount is the incoming purchase price. Rows already loaded
into period_price are moved so the UI is correct before the next CSV sync.
updated_at changes the free-catalog export fingerprint, so the next
unfiltered XLSX is rebuilt from the database.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0041_aurora_fee_buy_price"
down_revision: Union[str, None] = "0040_twilio_numbers_resume"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MOVE_TO_BUY = """
UPDATE numbers_catalog_normalized AS n
SET buy_price = n.period_price,
    period_price = NULL,
    updated_at = now()
FROM providers AS p
WHERE n.provider_id = p.id
  AND p.code = 'aurora'
  AND n.inventory_kind = 'free'
  AND n.period_price IS NOT NULL
  AND n.buy_price IS NULL
"""

_MOVE_TO_PERIOD = """
UPDATE numbers_catalog_normalized AS n
SET period_price = n.buy_price,
    buy_price = NULL,
    updated_at = now()
FROM providers AS p
WHERE n.provider_id = p.id
  AND p.code = 'aurora'
  AND n.inventory_kind = 'free'
  AND n.buy_price IS NOT NULL
  AND n.period_price IS NULL
"""


def upgrade() -> None:
    op.execute(_MOVE_TO_BUY)


def downgrade() -> None:
    op.execute(_MOVE_TO_PERIOD)
