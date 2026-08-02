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
    """
    Bucket for free inventory IF/WHEN docs confirm a source endpoint.
    Currently capability-limited — do not populate from guessed endpoints.
    TODO: VERIFY_WITH_DOC_FILE — free inventory endpoint mapping
    """

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
    """
    Bucket for purchased inventory IF/WHEN docs confirm a source endpoint.
    Currently capability-limited.
    TODO: VERIFY_WITH_DOC_FILE — purchased inventory endpoint mapping
    """

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
