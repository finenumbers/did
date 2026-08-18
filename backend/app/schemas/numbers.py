from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NumberItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    provider_code: str
    inventory_kind: str
    provider_number_key: str
    msisdn: str | None = None
    abc_code: str | None = None
    number_category: str | None = None
    number_local: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    buy_price: Decimal | None = None
    period_price: Decimal | None = None
    mask: str | None = None
    display_mask: str | None = None
    number_type: str | None = None
    points: Decimal | None = None
    notes: str | None = None
    number_class: str | None = Field(default=None, serialization_alias="class")
    operator: str | None = None
    rtu_connected: str | None = None
    is_currently_present: bool
    mapping_confidence: str


class FacetItem(BaseModel):
    value: str
    count: int


class FacetResponse(BaseModel):
    column: str
    items: list[FacetItem]
    truncated: bool
