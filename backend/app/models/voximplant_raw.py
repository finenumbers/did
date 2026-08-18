"""Voximplant raw tables. Docs: docs/providers/voximplant-contract.md."""

from sqlalchemy import Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class VoximplantRegionRaw(RawSyncMixin, Base):
    """GetPhoneNumberRegions rows (composite key category:region_id)."""

    __tablename__ = "voximplant_regions_raw"

    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_region_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    phone_installation_price: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )


class VoximplantCityRaw(RawSyncMixin, Base):
    """Region projected as city for catalog geo join."""

    __tablename__ = "voximplant_cities_raw"

    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    eng_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class VoximplantCategoryRaw(RawSyncMixin, Base):
    """GetPhoneNumberCategories RU listable categories."""

    __tablename__ = "voximplant_categories_raw"

    category_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class VoximplantFreeNumberRaw(RawSyncMixin, Base):
    """GetNewPhoneNumbers rows (merged RU slices)."""

    __tablename__ = "voximplant_free_numbers_raw"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    subscription_fee: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
