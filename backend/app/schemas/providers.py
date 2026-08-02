from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProviderCapability(BaseModel):
    supported: bool
    source: str | None = None
    action: str | None = None
    actions: list[str] | None = None
    reason_code: str | None = None
    doc_refs: list[str] | None = None


class ProviderOut(BaseModel):
    id: UUID
    code: str
    name: str
    is_enabled: bool
    capabilities: dict[str, ProviderCapability]
    last_tested_at: datetime | None = None
    last_test_status: str | None = None

    model_config = {"from_attributes": True}


class ProviderSettingsOut(BaseModel):
    provider_code: str
    base_url: str | None = None
    auth_settings_masked: dict[str, Any] = Field(default_factory=dict)
    extra_settings: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_test_message: str | None = None
    docs_notice: str = (
        "Provider integration is based on uploaded documentation contracts "
        "under docs/providers/*-contract.md"
    )


class ProviderSettingsUpdate(BaseModel):
    base_url: str | None = None
    auth_settings: dict[str, Any] | None = None
    extra_settings: dict[str, Any] | None = None
    is_enabled: bool | None = None


class TestConnectionOut(BaseModel):
    ok: bool
    message: str
    checked_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class ProviderHealthOut(BaseModel):
    provider_code: str
    connection_status: str
    last_tested_at: datetime | None
    free_count: int
    purchased_count: int
    capabilities: dict[str, ProviderCapability]
    limitations: list[str] = Field(default_factory=list)
