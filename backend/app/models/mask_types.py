"""Directory of beauty-mask combinations for the «Маски и типы» page."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MaskType(Base, TimestampMixin):
    """One unique combination: digit capacity + category + ABC + mask."""

    __tablename__ = "mask_types"
    __table_args__ = (
        UniqueConstraint(
            "digit_capacity",
            "category",
            "abc",
            "mask",
            name="uq_mask_types_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    digit_capacity: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="")
    abc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mask: Mapped[str] = mapped_column(Text, nullable=False)
    type_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    premium: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    purchase: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    period: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
