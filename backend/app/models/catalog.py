"""Normalized catalog and change history."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import HistoryChangeSource, InventoryKind, MappingConfidence


class NumbersCatalogNormalized(Base, TimestampMixin):
    """Cross-provider UI catalog."""

    __tablename__ = "numbers_catalog_normalized"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "inventory_kind",
            "provider_number_key",
            name="uq_catalog_provider_kind_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    inventory_kind: Mapped[InventoryKind] = mapped_column(
        Enum(InventoryKind, name="inventory_kind"), nullable=False, index=True
    )
    provider_number_key: Mapped[str] = mapped_column(Text, nullable=False)
    msisdn: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    abc_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    buy_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    period_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Runexis Numbering free extras (SipOut free leaves these NULL)
    # has_sms / tariff_name / price_currency / status_normalized: raw-only (not in catalog)
    mask: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_mask: Mapped[str | None] = mapped_column(Text, nullable=True)
    book_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    date_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_fas: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_operation_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    abcdef: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SipOut purchased extras
    order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_required: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_doc_required: Mapped[str | None] = mapped_column(Text, nullable=True)
    sign: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Runexis purchased extras (nested object → display label)
    tariff: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_class: Mapped[str | None] = mapped_column("class", Text, nullable=True)
    operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    partner: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment: Mapped[str | None] = mapped_column(Text, nullable=True)
    rtu_connected: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_source_table: Mapped[str] = mapped_column(Text, nullable=False)
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_sync_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=True
    )
    field_verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    mapping_confidence: Mapped[MappingConfidence] = mapped_column(
        Enum(MappingConfidence, name="mapping_confidence"),
        nullable=False,
        default=MappingConfidence.low,
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_currently_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    normalized_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class NumberPriceHistory(Base):
    __tablename__ = "number_price_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("numbers_catalog_normalized.id"), nullable=False, index=True
    )
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    new_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"))
    change_source: Mapped[HistoryChangeSource] = mapped_column(
        Enum(HistoryChangeSource, name="history_change_source"),
        nullable=False,
        default=HistoryChangeSource.sync,
    )
    raw_source_table: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class NumberStatusHistory(Base):
    __tablename__ = "number_status_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("numbers_catalog_normalized.id"), nullable=False, index=True
    )
    old_status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_status_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_status_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"))
    change_source: Mapped[HistoryChangeSource] = mapped_column(
        Enum(HistoryChangeSource, name="history_change_source", create_type=False),
        nullable=False,
        default=HistoryChangeSource.sync,
    )
    raw_source_table: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
