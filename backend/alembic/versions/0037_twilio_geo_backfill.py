"""One-shot Twilio geo classify from region_raw / locality_raw

Revision ID: 0037_twilio_geo_backfill
Revises: 0036_twilio_geo_classify
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_twilio_geo_backfill"
down_revision: Union[str, None] = "0036_twilio_geo_classify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    from app.modules.twilio.persist import backfill_classified_geo

    backfill_classified_geo(op.get_bind())


def downgrade() -> None:
    pass
