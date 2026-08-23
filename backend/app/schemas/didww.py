from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DidwwGroupItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_group_key: str
    country_name: str | None = None
    country_iso: str | None = None
    country_prefix: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    area_prefix: str | None = None
    did_type: str | None = None
    buy_price: Decimal | None = None
    period_price: Decimal | None = None
    channels_included: int | None = None
    stock_count: int | None = None
    number_select: bool | None = None
    features: str | None = None
    needs_registration: bool | None = None
    is_metered: bool | None = None


class DidwwFacetItem(BaseModel):
    value: str
    count: int


class DidwwFacetResponse(BaseModel):
    column: str
    items: list[DidwwFacetItem]
    truncated: bool


class DidwwSyncStageOut(BaseModel):
    id: str
    group: str
    label: str
    status: str
    detail: str = ""
    started_at: str | None = None
    finished_at: str | None = None


class DidwwSyncJobOut(BaseModel):
    id: UUID
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None
    triggered_by: str | None = None
    created_at: datetime
    counts: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    stages: list[DidwwSyncStageOut] = Field(default_factory=list)


class DidwwAvailableDidOut(BaseModel):
    id: str
    number: str | None = None
    did_group_id: str | None = None
