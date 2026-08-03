"""Remove non-free Runexis rows from free catalog (status 3/4/…).

Revision ID: 0014_purge_runexis_non_free
Revises: 0013_number_category
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014_purge_runexis_non_free"
down_revision: Union[str, None] = "0013_number_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop history then catalog rows that are not free/0 so the next free sync
    # wipe-guard compares against a free-only baseline.
    op.execute(
        """
        DELETE FROM number_price_history
        WHERE catalog_id IN (
          SELECT n.id
          FROM numbers_catalog_normalized n
          JOIN providers p ON p.id = n.provider_id
          WHERE p.code = 'runexis'
            AND n.inventory_kind = 'free'
            AND n.status_raw IS NOT NULL
            AND lower(btrim(n.status_raw::text)) NOT IN ('free', '0')
        )
        """
    )
    op.execute(
        """
        DELETE FROM number_status_history
        WHERE catalog_id IN (
          SELECT n.id
          FROM numbers_catalog_normalized n
          JOIN providers p ON p.id = n.provider_id
          WHERE p.code = 'runexis'
            AND n.inventory_kind = 'free'
            AND n.status_raw IS NOT NULL
            AND lower(btrim(n.status_raw::text)) NOT IN ('free', '0')
        )
        """
    )
    op.execute(
        """
        DELETE FROM numbers_catalog_normalized n
        USING providers p
        WHERE n.provider_id = p.id
          AND p.code = 'runexis'
          AND n.inventory_kind = 'free'
          AND n.status_raw IS NOT NULL
          AND lower(btrim(n.status_raw::text)) NOT IN ('free', '0')
        """
    )


def downgrade() -> None:
    # Irreversible data cleanup
    pass
