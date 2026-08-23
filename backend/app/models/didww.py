"""DIDWW raw dictionaries + isolated coverage catalog (not numbers_catalog_normalized)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class DidwwCountryRaw(RawSyncMixin, Base):
    __tablename__ = "didww_countries_raw"

    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    iso: Mapped[str | None] = mapped_column(Text, nullable=True)
    prefix: Mapped[str | None] = mapped_column(Text, nullable=True)


class DidwwRegionRaw(RawSyncMixin, Base):
    __tablename__ = "didww_regions_raw"

    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    iso: Mapped[str | None] = mapped_column(Text, nullable=True)


class DidwwCityRaw(RawSyncMixin, Base):
    __tablename__ = "didww_cities_raw"

    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class DidwwDidGroupTypeRaw(RawSyncMixin, Base):
    __tablename__ = "didww_did_group_types_raw"

    name: Mapped[str | None] = mapped_column(Text, nullable=True)


class DidwwDidGroupRaw(RawSyncMixin, Base):
    __tablename__ = "didww_did_groups_raw"

    prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True)


class DidwwCatalog(Base):
    """One row = one DID Group (coverage), not an E.164."""

    __tablename__ = "didww_catalog"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_group_key", name="uq_didww_catalog_provider_group"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    provider_group_key: Mapped[str] = mapped_column(Text, nullable=False)
    country_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    country_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_prefix: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    did_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    buy_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    period_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    channels_included: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_select: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    features: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_registration: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_metered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    skus_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    field_verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_sync_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_currently_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
