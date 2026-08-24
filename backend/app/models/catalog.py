"""Normalized catalog and change history."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import HistoryChangeSource, InventoryKind


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
    type_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    premium: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    mask_purchase: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    client: Mapped[str | None] = mapped_column(Text, nullable=True)
    rtu_connected: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_source_table: Mapped[str] = mapped_column(Text, nullable=False)
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_sync_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=True
    )
    field_verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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
