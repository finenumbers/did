from datetime import datetime
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
    status_raw: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    buy_price: Decimal | None = None
    period_price: Decimal | None = None
    mask: str | None = None
    display_mask: str | None = None
    book_date: str | None = None
    number_type: str | None = None
    points: Decimal | None = None
    date_from: str | None = None
    operator_fas: str | None = None
    operator_id: str | None = None
    last_operation_date: str | None = None
    manager_id: str | None = None
    notes: str | None = None
    abcdef: str | None = None
    order_id: str | None = None
    doc_status: str | None = None
    doc_required: str | None = None
    order_doc_required: str | None = None
    sign: str | None = None
    tariff: str | None = None
    number_class: str | None = Field(default=None, serialization_alias="class")
    operator: str | None = None
    partner: str | None = None
    project: str | None = None
    equipment: str | None = None
    last_seen_at: datetime
    is_currently_present: bool
    mapping_confidence: str
    field_verification: dict[str, str] = Field(default_factory=dict)


class FacetItem(BaseModel):
    value: str
    count: int


class FacetResponse(BaseModel):
    column: str
    items: list[FacetItem]
    truncated: bool
