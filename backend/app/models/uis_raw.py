"""UIS raw tables. Docs: docs/providers/uis-contract.md."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class UisFreeNumberRaw(RawSyncMixin, Base):
    """VERIFIED method get.available_virtual_numbers."""

    __tablename__ = "uis_free_numbers_raw"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_mnemonic: Mapped[str | None] = mapped_column(Text, nullable=True)


class UisPurchasedNumberRaw(RawSyncMixin, Base):
    """VERIFIED method get.virtual_numbers."""

    __tablename__ = "uis_purchased_numbers_raw"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
