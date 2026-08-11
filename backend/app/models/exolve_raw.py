"""Exolve raw tables. Docs: docs/providers/exolve-contract.md."""

from sqlalchemy import Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class ExolveRegionRaw(RawSyncMixin, Base):
    """GetList.regions — every region row (no filtering)."""

    __tablename__ = "exolve_regions_raw"

    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_region_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExolveCityRaw(RawSyncMixin, Base):
    """Leaf regions from GetList (parent_region_id set) projected as cities."""

    __tablename__ = "exolve_cities_raw"

    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExolveCategoryRaw(RawSyncMixin, Base):
    """GetList.categories snapshot."""

    __tablename__ = "exolve_categories_raw"

    category_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExolveFreeNumberRaw(RawSyncMixin, Base):
    """GetFree NumberElement rows (merged type×region slices)."""

    __tablename__ = "exolve_free_numbers_raw"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    type_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    subscription_fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
