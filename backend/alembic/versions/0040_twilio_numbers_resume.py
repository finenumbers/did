"""Twilio numbers checkpoint / heartbeat + coverage count index

Revision ID: 0040_twilio_numbers_resume
Revises: 0039_twilio_list_idx
Create Date: 2026-09-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_twilio_numbers_resume"
down_revision: Union[str, None] = "0039_twilio_list_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "twilio_catalog",
        sa.Column("numbers_checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("twilio_catalog", sa.Column("numbers_last_error", sa.Text(), nullable=True))
    op.add_column(
        "twilio_catalog",
        sa.Column("numbers_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_twilio_numbers_coverage",
        "twilio_available_numbers",
        ["provider_id", "country_iso", "number_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_twilio_numbers_coverage", table_name="twilio_available_numbers")
    op.drop_column("twilio_catalog", "numbers_heartbeat_at")
    op.drop_column("twilio_catalog", "numbers_last_error")
    op.drop_column("twilio_catalog", "numbers_checkpoint")
