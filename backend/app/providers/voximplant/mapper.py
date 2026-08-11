"""Voximplant → NormalizedNumber. See docs/providers/voximplant-field-mapping.md."""

from __future__ import annotations

from typing import Any

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.msisdn_split import split_from_parts
from app.providers.voximplant import contract


def map_number(
    item: ParsedNumberItem,
    *,
    inventory_kind: InventoryKind = InventoryKind.free,
) -> NormalizedNumber | None:
    if inventory_kind != InventoryKind.free:
        return None
    if not item.provider_number_key:
        return None

    abc_code, number_local = split_from_parts(msisdn=item.msisdn)
    confidence = (
        MappingConfidence.high
        if item.msisdn and (item.city_name or item.region_name)
        else MappingConfidence.medium
    )
    tax = {}
    raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    if raw.get("phone_tax_reserve") is not None:
        tax["phone_tax_reserve"] = raw.get("phone_tax_reserve")
    if raw.get("phone_installation_tax_reserve") is not None:
        tax["phone_installation_tax_reserve"] = raw.get("phone_installation_tax_reserve")
    if raw.get("phone_id") is not None:
        tax["phone_id"] = raw.get("phone_id")

    return NormalizedNumber(
        inventory_kind=InventoryKind.free,
        provider_number_key=item.provider_number_key,
        msisdn=item.msisdn,
        abc_code=abc_code,
        number_local=number_local,
        city_external_id=item.city_external_id,
        region_external_id=item.region_external_id,
        city_name=item.city_name,
        region_name=item.region_name,
        buy_price=item.buy_price,
        period_price=item.period_price,
        status_raw=item.status_raw or contract.STATUS_FREE,
        number_type=item.number_type,
        number_class=item.number_class,
        mapping_confidence=confidence,
        normalized_payload={
            "provider_number_key": item.provider_number_key,
            "category_name": item.number_class,
            **tax,
        },
        raw_payload=raw,
    )


def category_raw_rows(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in categories:
        name = row.get("phone_category_name")
        if not name:
            continue
        key = str(name).strip()
        out.append(
            {
                "category_external_id": key,
                "category_name": key,
                "type_id": None,
                "type_name": key,
                "raw_payload": row,
            }
        )
    return out
