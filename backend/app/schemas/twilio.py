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
    region_count: int = 0
    city_count: int = 0
    number_count: int = 0
    numbers_synced_at: datetime | None = None
    numbers_loaded: bool = False


class TwilioNumberItem(BaseModel):
    id: UUID
    phone_number: str
    country_name: str | None = None
    country_iso: str | None = None
    number_type: str | None = None
    region: str | None = None
    locality: str | None = None
    period_price: Decimal | None = None
    price_unit: str | None = None
    voice: bool | None = None
    sms: bool | None = None
    mms: bool | None = None
    fax: bool | None = None
    address_requirements: str | None = None


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
    last_success_at: datetime | None = None
    has_catalog: bool = False


class TwilioNumbersSyncIn(BaseModel):
    country_iso: str
    number_type: str


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


class TwilioSampleProbeStageOut(BaseModel):
    id: str
    label: str
    status: str
    detail: str = ""


class TwilioSampleProbeRecentOut(BaseModel):
    request_n: int | None = None
    detail: str
    stage: str | None = None


class TwilioSampleProbeOut(BaseModel):
    exists: bool
    running: bool
    status: str
    started_at: str | None = None
    updated_at: str | None = None
    elapsed_s: float | None = None
    requests: int = 0
    cities_total: int = 0
    numbers_total: int = 0
    numbers_after_stage2: int = 0
    by_country: dict[str, Any] = Field(default_factory=dict)
    current_detail: str = ""
    stages: list[TwilioSampleProbeStageOut] = Field(default_factory=list)
    recent: list[TwilioSampleProbeRecentOut] = Field(default_factory=list)
