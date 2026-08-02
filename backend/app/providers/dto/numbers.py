from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.enums import FieldVerification, InventoryKind, MappingConfidence


@dataclass
class ParsedNumberItem:
    raw_payload: dict[str, Any]
    provider_number_key: str | None = None
    msisdn: str | None = None
    city_external_id: str | None = None
    region_external_id: str | None = None
    city_name: str | None = None
    region_name: str | None = None
    price_amount: Decimal | None = None
    status_raw: str | None = None
    has_sms: bool | None = None
    tariff_name: str | None = None
    field_verification: dict[str, FieldVerification] = field(default_factory=dict)


@dataclass
class NormalizedNumber:
    inventory_kind: InventoryKind
    provider_number_key: str
    msisdn: str | None
    city_external_id: str | None
    region_external_id: str | None
    city_name: str | None
    region_name: str | None
    price_amount: Decimal | None
    price_currency: str | None
    status_raw: str | None
    has_sms: bool | None
    tariff_name: str | None
    field_verification: dict[str, str]
    mapping_confidence: MappingConfidence
    normalized_payload: dict[str, Any]
    raw_payload: dict[str, Any]
