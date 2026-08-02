"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

provider_code = postgresql.ENUM("runexis", "sipout", name="provider_code", create_type=False)
inventory_kind = postgresql.ENUM("free", "purchased", name="inventory_kind", create_type=False)
sync_job_type = postgresql.ENUM(
    "free_numbers",
    "purchased_numbers",
    "regions",
    "cities",
    "connection_test",
    "full",
    "free_only",
    "purchased_only",
    "dictionaries_only",
    name="sync_job_type",
    create_type=False,
)
sync_job_status = postgresql.ENUM(
    "pending",
    "running",
    "success",
    "failed",
    "partial",
    name="sync_job_status",
    create_type=False,
)
sync_log_level = postgresql.ENUM(
    "debug", "info", "warning", "error", name="sync_log_level", create_type=False
)
connection_test_status = postgresql.ENUM(
    "never_tested", "ok", "failed", name="connection_test_status", create_type=False
)
mapping_confidence = postgresql.ENUM(
    "low", "medium", "high", name="mapping_confidence", create_type=False
)
history_change_source = postgresql.ENUM(
    "sync", "manual", "system", name="history_change_source", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (
        postgresql.ENUM("runexis", "sipout", name="provider_code"),
        postgresql.ENUM("free", "purchased", name="inventory_kind"),
        postgresql.ENUM(
            "free_numbers",
            "purchased_numbers",
            "regions",
            "cities",
            "connection_test",
            "full",
            "free_only",
            "purchased_only",
            "dictionaries_only",
            name="sync_job_type",
        ),
        postgresql.ENUM(
            "pending", "running", "success", "failed", "partial", name="sync_job_status"
        ),
        postgresql.ENUM("debug", "info", "warning", "error", name="sync_log_level"),
        postgresql.ENUM(
            "never_tested", "ok", "failed", name="connection_test_status"
        ),
        postgresql.ENUM("low", "medium", "high", name="mapping_confidence"),
        postgresql.ENUM("sync", "manual", "system", name="history_change_source"),
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", provider_code, nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "provider_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("auth_settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("extra_settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", connection_test_status, nullable=False, server_default="never_tested"),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider_id", name="uq_provider_connections_provider"),
    )
    op.create_table(
        "system_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("job_type", sync_job_type, nullable=False),
        sa.Column("status", sync_job_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sync_jobs_provider_id", "sync_jobs", ["provider_id"])
    op.create_table(
        "sync_job_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sync_log_level, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sync_job_logs_sync_job_id", "sync_job_logs", ["sync_job_id"])

    def raw_table(name: str, extra_cols: list):
        cols = [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
            sa.Column("source_loaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
            sa.Column("payload_hash", sa.Text(), nullable=True),
            sa.Column("external_key", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            *extra_cols,
        ]
        op.create_table(name, *cols)
        op.create_index(f"ix_{name}_sync_job_id", name, ["sync_job_id"])
        op.create_index(f"ix_{name}_external_key", name, ["external_key"])

    raw_table(
        "runexis_regions_raw",
        [
            sa.Column("region_external_id", sa.Text()),
            sa.Column("name", sa.Text()),
        ],
    )
    raw_table(
        "runexis_cities_raw",
        [
            sa.Column("city_external_id", sa.Text()),
            sa.Column("city_name", sa.Text()),
            sa.Column("region_external_id", sa.Text()),
            sa.Column("region_name", sa.Text()),
        ],
    )
    number_extras = [
        sa.Column("source_endpoint", sa.Text()),
        sa.Column("region_code", sa.Text()),
        sa.Column("phone_number", sa.Text()),
        sa.Column("number_code", sa.Text()),
        sa.Column("number_local", sa.Text()),
        sa.Column("city_external_id", sa.Text()),
        sa.Column("region_name", sa.Text()),
        sa.Column("city_name", sa.Text()),
        sa.Column("status_raw", sa.Text()),
        sa.Column("price_installation", sa.Numeric(18, 4)),
        sa.Column("price_subscription", sa.Numeric(18, 4)),
        sa.Column("price_mera", sa.Numeric(18, 4)),
    ]
    raw_table("runexis_free_numbers_raw", number_extras)
    raw_table("runexis_purchased_numbers_raw", number_extras)
    raw_table(
        "sipout_regions_raw",
        [
            sa.Column("region_external_id", sa.Text()),
            sa.Column("name", sa.Text()),
            sa.Column("eng_name", sa.Text()),
            sa.Column("capital_city", sa.Text()),
            sa.Column("gmt", sa.Text()),
        ],
    )
    raw_table(
        "sipout_cities_raw",
        [
            sa.Column("city_external_id", sa.Text()),
            sa.Column("name", sa.Text()),
            sa.Column("eng_name", sa.Text()),
            sa.Column("region_external_id", sa.Text()),
        ],
    )
    raw_table(
        "sipout_free_numbers_raw",
        [
            sa.Column("did", sa.Text()),
            sa.Column("price", sa.Text()),
            sa.Column("city_id", sa.Text()),
        ],
    )
    op.create_index("ix_sipout_free_numbers_raw_did", "sipout_free_numbers_raw", ["did"])
    raw_table(
        "sipout_purchased_numbers_raw",
        [
            sa.Column("did", sa.Text()),
            sa.Column("user_comment", sa.Text()),
            sa.Column("order_id", sa.Text()),
            sa.Column("doc_status", sa.Text()),
            sa.Column("status", sa.Text()),
            sa.Column("city_id", sa.Text()),
            sa.Column("has_sms", sa.Text()),
            sa.Column("sign", sa.Text()),
        ],
    )
    op.create_index("ix_sipout_purchased_numbers_raw_did", "sipout_purchased_numbers_raw", ["did"])

    op.create_table(
        "numbers_catalog_normalized",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("inventory_kind", inventory_kind, nullable=False),
        sa.Column("provider_number_key", sa.Text(), nullable=False),
        sa.Column("msisdn", sa.Text()),
        sa.Column("region_external_id", sa.Text()),
        sa.Column("city_external_id", sa.Text()),
        sa.Column("region_name", sa.Text()),
        sa.Column("city_name", sa.Text()),
        sa.Column("price_amount", sa.Numeric(18, 4)),
        sa.Column("price_currency", sa.Text()),
        sa.Column("status_raw", sa.Text()),
        sa.Column("status_normalized", sa.Text()),
        sa.Column("has_sms", sa.Boolean()),
        sa.Column("tariff_name", sa.Text()),
        sa.Column("raw_source_table", sa.Text(), nullable=False),
        sa.Column("raw_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id")),
        sa.Column("field_verification", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("mapping_confidence", mapping_confidence, nullable=False, server_default="low"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_currently_present", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("normalized_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider_id", "inventory_kind", "provider_number_key", name="uq_catalog_provider_kind_key"),
    )
    op.create_index("ix_catalog_provider_id", "numbers_catalog_normalized", ["provider_id"])
    op.create_index("ix_catalog_inventory_kind", "numbers_catalog_normalized", ["inventory_kind"])
    op.create_index("ix_catalog_msisdn", "numbers_catalog_normalized", ["msisdn"])
    op.create_index("ix_catalog_last_seen_at", "numbers_catalog_normalized", ["last_seen_at"])

    op.create_table(
        "number_price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("numbers_catalog_normalized.id"), nullable=False),
        sa.Column("old_price", sa.Numeric(18, 4)),
        sa.Column("new_price", sa.Numeric(18, 4)),
        sa.Column("currency", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id")),
        sa.Column("change_source", history_change_source, nullable=False),
        sa.Column("raw_source_table", sa.Text()),
        sa.Column("raw_source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_price_history_catalog_id", "number_price_history", ["catalog_id"])

    op.create_table(
        "number_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("numbers_catalog_normalized.id"), nullable=False),
        sa.Column("old_status_raw", sa.Text()),
        sa.Column("new_status_raw", sa.Text()),
        sa.Column("old_status_normalized", sa.Text()),
        sa.Column("new_status_normalized", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id")),
        sa.Column("change_source", history_change_source, nullable=False),
        sa.Column("raw_source_table", sa.Text()),
        sa.Column("raw_source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_status_history_catalog_id", "number_status_history", ["catalog_id"])


def downgrade() -> None:
    for t in [
        "number_status_history",
        "number_price_history",
        "numbers_catalog_normalized",
        "sipout_purchased_numbers_raw",
        "sipout_free_numbers_raw",
        "sipout_cities_raw",
        "sipout_regions_raw",
        "runexis_purchased_numbers_raw",
        "runexis_free_numbers_raw",
        "runexis_cities_raw",
        "runexis_regions_raw",
        "sync_job_logs",
        "sync_jobs",
        "system_settings",
        "provider_connections",
        "providers",
    ]:
        op.drop_table(t)
    for e in [
        history_change_source,
        mapping_confidence,
        connection_test_status,
        sync_log_level,
        sync_job_status,
        sync_job_type,
        inventory_kind,
        provider_code,
    ]:
        e.drop(op.get_bind(), checkfirst=True)
