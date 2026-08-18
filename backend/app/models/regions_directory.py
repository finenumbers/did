"""Local ABC / city / region directory for the Regions page (XLSX import)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RegionsDirectory(Base):
    """Rows shown on «Регионы». Filled only by XLSX import, not by sync."""

    __tablename__ = "regions_directory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    abc: Mapped[str] = mapped_column(Text, nullable=False)
    digit_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    city_name: Mapped[str] = mapped_column(Text, nullable=False)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
