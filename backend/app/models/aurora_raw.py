"""Aurora Telecom raw tables. Docs: docs/providers/aurora-contract.md."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, RawSyncMixin


class AuroraFreeNumberRaw(RawSyncMixin, Base):
    """VERIFIED live free inventory from regional Aurora CSVs (merged)."""

    __tablename__ = "aurora_free_numbers_raw"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    period_price_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_mask: Mapped[str | None] = mapped_column(Text, nullable=True)
