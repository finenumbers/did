from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models.enums import InventoryKind, MappingConfidence


@dataclass
class ParsedNumberItem:
    raw_payload: dict[str, Any]
    provider_number_key: str | None = None
    msisdn: str | None = None
    city_external_id: str | None = None
    region_external_id: str | None = None
    city_name: str | None = None
    region_name: str | None = None
    buy_price: Decimal | None = None
    period_price: Decimal | None = None
    status_raw: str | None = None
    # Kept for SipOut purchased raw typed column; not mapped to catalog
    has_sms: bool | None = None
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
    # SipOut purchased → catalog
    order_id: str | None = None
    doc_status: str | None = None
    doc_required: str | None = None
    order_doc_required: str | None = None
    sign: str | None = None
    # Runexis purchased → catalog (display labels)
    tariff: str | None = None
    number_class: str | None = None
    operator: str | None = None
    partner: str | None = None
    project: str | None = None
    equipment: str | None = None


@dataclass
class NormalizedNumber:
    inventory_kind: InventoryKind
    provider_number_key: str
    msisdn: str | None
    city_external_id: str | None
    region_external_id: str | None
    city_name: str | None
    region_name: str | None
    buy_price: Decimal | None
    period_price: Decimal | None
    status_raw: str | None
    mapping_confidence: MappingConfidence
    normalized_payload: dict[str, Any]
    raw_payload: dict[str, Any]
    abc_code: str | None = None
    number_local: str | None = None
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
    number_class: str | None = None
    operator: str | None = None
    partner: str | None = None
    project: str | None = None
    equipment: str | None = None
