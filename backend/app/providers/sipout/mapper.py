"""SipOut field mapping isolation. See docs/providers/sipout-field-mapping.md."""

from __future__ import annotations

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.msisdn_split import split_from_parts


def map_number(
    item: ParsedNumberItem,
    *,
    inventory_kind: InventoryKind,
    city_name: str | None = None,
    region_name: str | None = None,
    region_external_id: str | None = None,
) -> NormalizedNumber | None:
    if not item.provider_number_key:
        return None
    verification = {k: v.value for k, v in item.field_verification.items()}
    if city_name:
        verification["city_name"] = "derived"
    if region_name:
        verification["region_name"] = "derived"
    verification.pop("has_sms", None)
    verification.pop("price_currency", None)
    purchased = inventory_kind == InventoryKind.purchased
    free = inventory_kind == InventoryKind.free
    abc_code, number_local = split_from_parts(msisdn=item.msisdn)
    if abc_code:
        verification["abc_code"] = "derived"
    if number_local:
        verification["number_local"] = "derived"
    return NormalizedNumber(
        inventory_kind=inventory_kind,
        provider_number_key=item.provider_number_key,
        msisdn=item.msisdn,
        abc_code=abc_code,
        number_local=number_local,
        city_external_id=item.city_external_id,
        region_external_id=region_external_id,
        city_name=city_name,
        region_name=region_name,
        buy_price=item.buy_price if free else None,
        period_price=item.period_price if free else None,
        status_raw=item.status_raw if purchased else None,
        field_verification=verification,
        mapping_confidence=MappingConfidence.low,
        normalized_payload={
            "did": item.provider_number_key,
            "raw_keys": list(item.raw_payload.keys()),
        },
        raw_payload=item.raw_payload,
        order_id=item.order_id if purchased else None,
        doc_status=item.doc_status if purchased else None,
        doc_required=item.doc_required if purchased else None,
        order_doc_required=item.order_doc_required if purchased else None,
        sign=item.sign if purchased else None,
    )
