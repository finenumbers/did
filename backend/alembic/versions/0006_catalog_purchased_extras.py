"""catalog purchased extras SipOut + Runexis

Revision ID: 0006_purchased_extras
Revises: 0005_display_book
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_purchased_extras"
down_revision: Union[str, None] = "0005_display_book"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SipOut purchased
    op.add_column("numbers_catalog_normalized", sa.Column("order_id", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("doc_status", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("doc_required", sa.Text(), nullable=True))
    op.add_column(
        "numbers_catalog_normalized", sa.Column("order_doc_required", sa.Text(), nullable=True)
    )
    op.add_column("numbers_catalog_normalized", sa.Column("sign", sa.Text(), nullable=True))
    # Runexis purchased (nested objects → display label)
    op.add_column("numbers_catalog_normalized", sa.Column("tariff", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("class", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("operator", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("partner", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("project", sa.Text(), nullable=True))
    op.add_column("numbers_catalog_normalized", sa.Column("equipment", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET
          order_id = NULLIF(BTRIM(r.raw_payload->>'order_id'), ''),
          doc_status = NULLIF(BTRIM(r.raw_payload->>'doc_status'), ''),
          doc_required = NULLIF(BTRIM(r.raw_payload->>'doc_required'), ''),
          order_doc_required = NULLIF(BTRIM(r.raw_payload->>'order_doc_required'), ''),
          sign = CASE
            WHEN r.raw_payload ? 'sign' AND jsonb_typeof(r.raw_payload->'sign') = 'boolean'
              THEN (r.raw_payload->>'sign')
            WHEN NULLIF(BTRIM(r.raw_payload->>'sign'), '') IS NOT NULL
              THEN BTRIM(r.raw_payload->>'sign')
            ELSE NULL
          END
        FROM sipout_purchased_numbers_raw AS r,
             providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'sipout'
          AND c.inventory_kind = 'purchased'
          AND c.raw_source_id = r.id
        """
    )

    op.execute(
        """
        UPDATE numbers_catalog_normalized AS c
        SET
          tariff = COALESCE(
            NULLIF(BTRIM(r.raw_payload->'tariff'->>'name'), ''),
            NULLIF(BTRIM(r.raw_payload->'tariff'->>'mnemonic'), ''),
            NULLIF(BTRIM(r.raw_payload->'tariff'->>'id'), '')
          ),
          class = COALESCE(
            NULLIF(BTRIM(r.raw_payload->'class'->>'name'), ''),
            NULLIF(BTRIM(r.raw_payload->'class'->>'mnemonic'), ''),
            NULLIF(BTRIM(r.raw_payload->'class'->>'id'), '')
          ),
          operator = COALESCE(
            NULLIF(BTRIM(r.raw_payload->'operator'->>'name'), ''),
            NULLIF(BTRIM(r.raw_payload->'operator'->>'id'), '')
          ),
          partner = COALESCE(
            NULLIF(BTRIM(r.raw_payload->'partner'->>'name'), ''),
            NULLIF(BTRIM(r.raw_payload->'partner'->>'id'), '')
          ),
          project = COALESCE(
            NULLIF(BTRIM(r.raw_payload->'project'->>'name'), ''),
            NULLIF(BTRIM(r.raw_payload->'project'->>'id'), '')
          ),
          equipment = COALESCE(
            NULLIF(BTRIM(r.raw_payload->'equipment'->>'name'), ''),
            NULLIF(BTRIM(r.raw_payload->'equipment'->>'id'), '')
          )
        FROM runexis_purchased_numbers_raw AS r,
             providers AS p
        WHERE c.provider_id = p.id
          AND p.code = 'runexis'
          AND c.inventory_kind = 'purchased'
          AND c.raw_source_id = r.id
        """
    )


def downgrade() -> None:
    for col in (
        "equipment",
        "project",
        "partner",
        "operator",
        "class",
        "tariff",
        "sign",
        "order_doc_required",
        "doc_required",
        "doc_status",
        "order_id",
    ):
        op.drop_column("numbers_catalog_normalized", col)
