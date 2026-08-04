"""Runexis raw tables. Doc: docs/providers/runexis/raw/Runexis.html"""

from decimal import Decimal

from sqlalchemy import Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class RunexisRegionRaw(RawSyncMixin, Base):
    """VERIFIED path GET api/v1/regions — EXAMPLE-CONFIRMED keys id/name."""

    __tablename__ = "runexis_regions_raw"

    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunexisCityRaw(RawSyncMixin, Base):
    """VERIFIED path GET api/v1/regions/cities — EXAMPLE-CONFIRMED city/region keys."""

    __tablename__ = "runexis_cities_raw"

    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunexisFreeNumberRaw(RawSyncMixin, Base):
    """Free inventory from Numbering API JSON-RPC search_numbers (status free/0)."""

    __tablename__ = "runexis_free_numbers_raw"

    source_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_installation: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_subscription: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_mera: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)


class RunexisPurchasedNumberRaw(RawSyncMixin, Base):
    """Purchased/partner inventory from GET api/v1/numbers/management (non-free statuses)."""

    __tablename__ = "runexis_purchased_numbers_raw"

    source_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_local: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_installation: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_subscription: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_mera: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
