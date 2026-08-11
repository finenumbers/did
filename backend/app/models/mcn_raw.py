"""MCN raw tables. Docs: docs/providers/mcn-contract.md."""

from sqlalchemy import Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class McnRegionRaw(RawSyncMixin, Base):
    __tablename__ = "mcn_regions_raw"

    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_region_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class McnCityRaw(RawSyncMixin, Base):
    __tablename__ = "mcn_cities_raw"

    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    free_numbers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class McnFreeNumberRaw(RawSyncMixin, Base):
    __tablename__ = "mcn_free_numbers_raw"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    type_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    subscription_fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
