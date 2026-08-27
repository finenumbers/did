"""Index for Twilio numbers default list sort

Revision ID: 0039_twilio_list_idx
Revises: 0038_twilio_iso_realign
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0039_twilio_list_idx"
down_revision: Union[str, None] = "0038_twilio_iso_realign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_twilio_numbers_list",
        "twilio_available_numbers",
        ["country_name", "phone_number", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_twilio_numbers_list", table_name="twilio_available_numbers")
