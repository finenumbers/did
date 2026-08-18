"""Local city/region directory for the Regions page (SipOut get_cities, manual load)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RegionsDirectory(Base):
    """Rows shown on «Регионы». Filled only by POST /api/v1/regions/load, not by main sync."""

    __tablename__ = "regions_directory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    abc: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_name: Mapped[str] = mapped_column(Text, nullable=False)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
