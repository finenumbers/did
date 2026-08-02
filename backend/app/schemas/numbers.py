from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class NumberItem(BaseModel):
    id: UUID
    provider_code: str
    inventory_kind: str
    provider_number_key: str
    msisdn: str | None = None
    status_raw: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    has_sms: bool | None = None
    tariff_name: str | None = None
    last_seen_at: datetime
    is_currently_present: bool
    mapping_confidence: str
    field_verification: dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}
