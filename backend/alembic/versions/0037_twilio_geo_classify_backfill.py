"""One-shot Twilio geo classify from region_raw / locality_raw

Revision ID: 0037_twilio_geo_classify_backfill
Revises: 0036_twilio_geo_classify
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0037_twilio_geo_classify_backfill"
down_revision: Union[str, None] = "0036_twilio_geo_classify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.modules.twilio.persist import backfill_classified_geo

    backfill_classified_geo(op.get_bind())


def downgrade() -> None:
    pass
