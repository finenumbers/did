"""Drop unused catalog columns and number_status_history

Revision ID: 0023_drop_catalog_fields
Revises: 0022_pstn_gar_territory
Create Date: 2026-08-18

Remove catalog-only extras that are no longer shown. Provider values stay in
raw tables / raw_payload. last_seen_at stays (sync presence + export fingerprint).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_drop_catalog_fields"
down_revision: Union[str, None] = "0022_pstn_gar_territory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP_INDEXES = (
    "ix_catalog_kind_present_status",
    "ix_catalog_kind_present_order_id",
    "ix_catalog_kind_present_partner",
    "ix_catalog_kind_present_operator_fas",
)

_DROP_COLUMNS = (
    "status_raw",
    "book_date",
    "date_from",
    "last_operation_date",
    "operator_id",
    "operator_fas",
    "manager_id",
    "abcdef",
    "order_id",
    "doc_status",
    "doc_required",
    "order_doc_required",
    "sign",
    "tariff",
    "partner",
    "project",
    "equipment",
)


def upgrade() -> None:
    for name in _DROP_INDEXES:
        op.drop_index(name, table_name="numbers_catalog_normalized")
    for col in _DROP_COLUMNS:
        op.drop_column("numbers_catalog_normalized", col)
    op.drop_table("number_status_history")
    op.execute("DROP TABLE IF EXISTS numbers_catalog_normalized_stg")


def downgrade() -> None:
    for col in _DROP_COLUMNS:
        op.add_column(
            "numbers_catalog_normalized",
            sa.Column(col, sa.Text(), nullable=True),
        )
    op.create_index(
        "ix_catalog_kind_present_status",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "status_raw"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_order_id",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "order_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_partner",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "partner"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_operator_fas",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "operator_fas"],
        unique=False,
    )
    history_change_source = postgresql.ENUM(
        name="history_change_source",
        create_type=False,
    )
    op.create_table(
        "number_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "catalog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("numbers_catalog_normalized.id"),
            nullable=False,
        ),
        sa.Column("old_status_raw", sa.Text()),
        sa.Column("new_status_raw", sa.Text()),
        sa.Column("old_status_normalized", sa.Text()),
        sa.Column("new_status_normalized", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id")),
        sa.Column("change_source", history_change_source, nullable=False),
        sa.Column("raw_source_table", sa.Text()),
        sa.Column("raw_source_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "meta",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_status_history_catalog_id",
        "number_status_history",
        ["catalog_id"],
    )
