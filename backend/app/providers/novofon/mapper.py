"""Novofon → NormalizedNumber. See docs/providers/novofon-field-mapping.md."""

from __future__ import annotations

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.msisdn_split import split_from_parts


def map_number(
    item: ParsedNumberItem,
    *,
    inventory_kind: InventoryKind,
) -> NormalizedNumber | None:
    foreign = item.raw_payload.get("foreign_catalog") is True
    key = item.provider_number_key or item.msisdn
    if not key:
        return None
    if not foreign and not item.msisdn:
        return None
    free = inventory_kind == InventoryKind.free
    purchased = inventory_kind == InventoryKind.purchased
    if foreign:
        abc_code = None
        number_local = _as_local(item.raw_payload.get("catalog_number_local"))
        city_name = item.city_name
        region_name = item.region_name
        msisdn = item.msisdn
    else:
        abc_code, number_local = split_from_parts(msisdn=item.msisdn)
        city_name = None
        region_name = None
        msisdn = item.msisdn
        key = item.msisdn or key
    return NormalizedNumber(
        inventory_kind=inventory_kind,
        provider_number_key=key,
        msisdn=msisdn,
        abc_code=abc_code,
        number_local=number_local,
        city_external_id=None,
        region_external_id=None,
        city_name=city_name,
        region_name=region_name,
        buy_price=item.buy_price if free else None,
        period_price=item.period_price if free or purchased else None,
        status_raw=item.status_raw if purchased else None,
        number_type=item.number_type,
        notes=None,
        date_from=item.date_from if purchased else None,
        mapping_confidence=MappingConfidence.medium,
        normalized_payload={
            "provider_number_key": key,
            "raw_keys": list(item.raw_payload.keys()),
        },
        raw_payload=item.raw_payload,
    )


def _as_local(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
