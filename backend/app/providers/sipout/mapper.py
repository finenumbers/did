"""SipOut field mapping isolation. See docs/providers/sipout-field-mapping.md."""

from __future__ import annotations

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem


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
    # Locked decision: price_amount only — no setup/monthly split
    verification.setdefault("price_currency", "unresolved")
    return NormalizedNumber(
        inventory_kind=inventory_kind,
        provider_number_key=item.provider_number_key,
        msisdn=item.msisdn,
        city_external_id=item.city_external_id,
        region_external_id=region_external_id,
        city_name=city_name,
        region_name=region_name,
        price_amount=item.price_amount if inventory_kind == InventoryKind.free else None,
        price_currency=None,  # TODO: VERIFY_WITH_DOC_FILE — currency not in docs
        status_raw=item.status_raw if inventory_kind == InventoryKind.purchased else None,
        has_sms=item.has_sms if inventory_kind == InventoryKind.purchased else None,
        tariff_name=None,  # not in connected_list docs
        field_verification=verification,
        mapping_confidence=MappingConfidence.low,
        normalized_payload={
            "did": item.provider_number_key,
            "raw_keys": list(item.raw_payload.keys()),
        },
        raw_payload=item.raw_payload,
    )


def map_region(item: ParsedRegion) -> ParsedRegion:
    return item


def map_city(item: ParsedCity) -> ParsedCity:
    return item
