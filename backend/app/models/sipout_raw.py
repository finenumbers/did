"""SipOut raw tables. Doc: docs/providers/sipout/raw/SipOut.html — method=did."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class SipoutRegionRaw(RawSyncMixin, Base):
    """VERIFIED action get_cities → data.regions; item keys EXAMPLE-CONFIRMED."""

    __tablename__ = "sipout_regions_raw"

    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    capital_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmt: Mapped[str | None] = mapped_column(Text, nullable=True)


class SipoutCityRaw(RawSyncMixin, Base):
    """VERIFIED action get_cities → data.cities; item keys EXAMPLE-CONFIRMED."""

    __tablename__ = "sipout_cities_raw"

    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class SipoutFreeNumberRaw(RawSyncMixin, Base):
    """VERIFIED action free_list; item keys EXAMPLE-CONFIRMED: did, price, city_id."""

    __tablename__ = "sipout_free_numbers_raw"

    did: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    price: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class SipoutPurchasedNumberRaw(RawSyncMixin, Base):
    """VERIFIED action connected_list; item keys EXAMPLE-CONFIRMED."""

    __tablename__ = "sipout_purchased_numbers_raw"

    did: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_id: Mapped[str | None] = mapped_column(Text, nullable=True)
