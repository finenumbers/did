"""Exolve → NormalizedNumber. See docs/providers/exolve-field-mapping.md."""

from __future__ import annotations

from typing import Any

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.exolve import contract
from app.providers.msisdn_split import split_from_parts


def map_number(
    item: ParsedNumberItem,
    *,
    inventory_kind: InventoryKind = InventoryKind.free,
    city_lookup: dict[str, tuple] | None = None,
) -> NormalizedNumber | None:
    if inventory_kind != InventoryKind.free:
        return None
    if not item.provider_number_key:
        return None

    city_lookup = city_lookup or {}
    city_id = item.city_external_id
    region_id = item.region_external_id
    city_name = item.city_name
    region_name = item.region_name

    # Prefer leaf city lookup (Cyrillic description); response region_name is Latin fallback.
    if city_id and city_id in city_lookup:
        tup = city_lookup[city_id]
        city_name = (tup[0] if tup else None) or city_name
        region_id = (tup[1] if len(tup) > 1 and tup[1] else None) or region_id
        region_name = (tup[2] if len(tup) > 2 and tup[2] else None) or region_name
    elif region_id and region_id in city_lookup:
        tup = city_lookup[region_id]
        city_id = region_id
        city_name = (tup[0] if tup else None) or city_name
        region_id = (tup[1] if len(tup) > 1 and tup[1] else None) or region_id
        region_name = (tup[2] if len(tup) > 2 and tup[2] else None) or region_name

    # KDU / Russia-only: no city
    if (item.number_type or "").upper() == "KDU" or region_id == str(
        contract.RUSSIA_REGION_ID
    ):
        if (item.number_type or "").upper() == "KDU":
            city_id = None
            city_name = None
            region_id = str(contract.RUSSIA_REGION_ID)
            region_name = region_name or "Россия"

    abc_code, number_local = split_from_parts(msisdn=item.msisdn)
    confidence = (
        MappingConfidence.high
        if item.msisdn and (city_name or region_name)
        else MappingConfidence.medium
    )
    return NormalizedNumber(
        inventory_kind=InventoryKind.free,
        provider_number_key=item.provider_number_key,
        msisdn=item.msisdn,
        abc_code=abc_code,
        number_local=number_local,
        city_external_id=city_id,
        region_external_id=region_id,
        city_name=city_name,
        region_name=region_name,
        buy_price=item.buy_price,
        period_price=item.period_price,
        status_raw=item.status_raw or contract.STATUS_FREE,
        number_type=item.number_type,
        number_class=item.number_class,
        mapping_confidence=confidence,
        normalized_payload={
            "provider_number_key": item.provider_number_key,
            "type_name": item.number_type,
            "category_name": item.number_class,
            "raw_keys": list(item.raw_payload.keys()),
        },
        raw_payload=item.raw_payload if isinstance(item.raw_payload, dict) else {},
    )


def category_raw_rows(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize category dicts for persist."""
    out: list[dict[str, Any]] = []
    for row in categories:
        cid = row.get("category_id")
        if cid is None:
            continue
        out.append(
            {
                "category_external_id": str(cid),
                "category_name": (
                    str(row.get("category_name")).strip()
                    if row.get("category_name") is not None
                    else None
                ),
                "type_id": (
                    str(row.get("type_id")) if row.get("type_id") is not None else None
                ),
                "type_name": (
                    str(row.get("type_name")).strip()
                    if row.get("type_name") is not None
                    else None
                ),
                "raw_payload": row,
            }
        )
    return out
