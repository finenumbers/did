"""MCN → NormalizedNumber. See docs/providers/mcn-field-mapping.md."""

from __future__ import annotations

from typing import Any

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.msisdn_split import split_from_parts
from app.providers.mcn import contract


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
    if city_id and city_id in city_lookup:
        tup = city_lookup[city_id]
        city_name = (tup[0] if tup else None) or city_name
        region_id = (tup[1] if len(tup) > 1 and tup[1] else None) or region_id
        region_name = (tup[2] if len(tup) > 2 and tup[2] else None) or region_name

    abc_code, number_local = split_from_parts(msisdn=item.msisdn)
    confidence = (
        MappingConfidence.high
        if item.msisdn and (city_name or region_name)
        else MappingConfidence.medium
    )
    raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
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
            "currency": raw.get("currency"),
            "beauty_level": raw.get("beauty_level"),
            "ndc_type_id": raw.get("ndc_type_id"),
            "source": raw.get("source"),
        },
        raw_payload=raw,
    )


def city_free_counts(cities_raw: list[dict[str, Any]]) -> list[tuple[int, int, str | None, str | None]]:
    """Return (city_id, free_count, city_name, region_name) for stock cities."""
    out: list[tuple[int, int, str | None, str | None]] = []
    for row in cities_raw:
        if not isinstance(row, dict):
            continue
        try:
            cid = int(row["city_id"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            cnt = int(row.get("free_numbers_count") or 0)
        except (TypeError, ValueError):
            cnt = 0
        if cnt <= 0:
            continue
        region = row.get("region") if isinstance(row.get("region"), dict) else {}
        out.append(
            (
                cid,
                cnt,
                str(row.get("city_name") or "").strip() or None,
                str(region.get("name") or "").strip() or None,
            )
        )
    return out
