"""Provider registry and connection settings."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ConnectionTestStatus, ProviderCode


class Provider(Base, TimestampMixin):
    """Independent external numbering source."""

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[ProviderCode] = mapped_column(Enum(ProviderCode, name="provider_code"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    connection: Mapped["ProviderConnection | None"] = relationship(back_populates="provider", uselist=False)


class ProviderConnection(Base, TimestampMixin):
    """Auth and connection settings for a provider."""

    __tablename__ = "provider_connections"
    __table_args__ = (UniqueConstraint("provider_id", name="uq_provider_connections_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False
    )
    # UNVERIFIED as mandatory: docs show example absolute URLs; overridable in settings.
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    extra_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[ConnectionTestStatus] = mapped_column(
        Enum(ConnectionTestStatus, name="connection_test_status"),
        nullable=False,
        default=ConnectionTestStatus.never_tested,
    )
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    provider: Mapped[Provider] = relationship(back_populates="connection")


class SystemSetting(Base):
    """System-wide key/value settings."""

    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
