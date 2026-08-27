"""Reassign leaked Twilio iso to the catalog country_name + type

Revision ID: 0038_twilio_iso_realign
Revises: 0037_twilio_geo_backfill
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0038_twilio_iso_realign"
down_revision: Union[str, None] = "0037_twilio_geo_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.modules.twilio.persist import REALIGN_ISO_SQL, recount_catalog_local_counts

    bind = op.get_bind()
    ids = bind.execute(text("SELECT DISTINCT provider_id FROM twilio_catalog")).all()
    for (provider_id,) in ids:
        bind.execute(text(REALIGN_ISO_SQL), {"provider_id": provider_id})
    recount_catalog_local_counts(bind)


def downgrade() -> None:
    pass
