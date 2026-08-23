"""Twilio raw dictionaries + isolated coverage catalog (not numbers_catalog_normalized)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class TwilioCountryRaw(RawSyncMixin, Base):
    __tablename__ = "twilio_countries_raw"

    country_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_beta: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class TwilioPricingRaw(RawSyncMixin, Base):
    __tablename__ = "twilio_pricing_raw"

    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_unit: Mapped[str | None] = mapped_column(Text, nullable=True)


class TwilioCatalog(Base):
    """One row = one country + number type (coverage), not an E.164."""

    __tablename__ = "twilio_catalog"
    __table_args__ = (
        UniqueConstraint("provider_id", "provider_group_key", name="uq_twilio_catalog_provider_group"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    provider_group_key: Mapped[str] = mapped_column(Text, nullable=False)
    country_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    number_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    period_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_beta: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    region_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    city_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


class TwilioGeo(Base):
    __tablename__ = "twilio_geo"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "country_iso",
            "number_type",
            "region_filter",
            "locality_norm",
            name="uq_twilio_geo_cell",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    country_iso: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    number_type: Mapped[str] = mapped_column(Text, nullable=False)
    region_filter: Mapped[str] = mapped_column(Text, nullable=False, default="")
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    locality: Mapped[str | None] = mapped_column(Text, nullable=True)
    locality_norm: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_sync_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TwilioAvailableNumber(Base):
    __tablename__ = "twilio_available_numbers"
    __table_args__ = (
        UniqueConstraint("provider_id", "phone_number", name="uq_twilio_available_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    phone_number: Mapped[str] = mapped_column(Text, nullable=False)
    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    country_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    number_type: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    locality: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    address_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sms: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mms: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fax: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="geo_sync")
    last_sync_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
