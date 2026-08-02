"""Unique partial index: at most one pending/running sync_run

Revision ID: 0012_single_active_sync_run
Revises: 0011_pstn_inn_cache
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012_single_active_sync_run"
down_revision: Union[str, None] = "0011_pstn_inn_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_runs_one_active
        ON sync_runs ((1))
        WHERE status IN ('pending', 'running')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sync_runs_one_active")
