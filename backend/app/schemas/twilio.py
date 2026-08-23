from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TwilioCoverageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_group_key: str
    country_name: str | None = None
    country_iso: str | None = None
    number_type: str | None = None
    period_price: Decimal | None = None
    price_unit: str | None = None
    country_beta: bool | None = None


class TwilioFacetItem(BaseModel):
    value: str
    count: int


class TwilioFacetResponse(BaseModel):
    column: str
    items: list[TwilioFacetItem]
    truncated: bool


class TwilioSyncStageOut(BaseModel):
    id: str
    group: str
    label: str
    status: str
    detail: str = ""
    started_at: str | None = None
    finished_at: str | None = None


class TwilioSyncJobOut(BaseModel):
    id: UUID
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None
    triggered_by: str | None = None
    created_at: datetime
    counts: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    stages: list[TwilioSyncStageOut] = Field(default_factory=list)


class TwilioAvailableNumberOut(BaseModel):
    phone_number: str | None = None
    friendly_name: str | None = None
    iso_country: str | None = None
    region: str | None = None
    locality: str | None = None
    postal_code: str | None = None
    lata: str | None = None
    rate_center: str | None = None
    address_requirements: str | None = None
    beta: bool | None = None
    voice: bool | None = None
    sms: bool | None = None
    mms: bool | None = None
    fax: bool | None = None


class TwilioAvailableNumbersResponse(BaseModel):
    items: list[TwilioAvailableNumberOut] = Field(default_factory=list)
    returned: int = 0
    same_set: bool = False
