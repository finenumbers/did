"""
Runexis field mapping isolation.
See docs/providers/runexis-field-mapping.md.
"""

from __future__ import annotations

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.msisdn_split import split_from_parts


def map_number(
    item: ParsedNumberItem,
    *,
    inventory_kind: InventoryKind,
    region_name: str | None = None,
    region_external_id: str | None = None,
) -> NormalizedNumber | None:
    if not item.provider_number_key:
        return None
    city_name = item.city_name
    purchased = inventory_kind == InventoryKind.purchased
    raw = item.raw_payload or {}
    abc_code, number_local = split_from_parts(
        msisdn=item.msisdn,
        code=raw.get("code") or raw.get("city_code"),
        number=raw.get("number") or raw.get("phone_number"),
    )
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
        buy_price=item.buy_price,
        period_price=item.period_price,
        status_raw=item.status_raw,
        mapping_confidence=MappingConfidence.low,
        normalized_payload={
            "code": item.raw_payload.get("code"),
            "number": item.raw_payload.get("number"),
            "status": item.raw_payload.get("status"),
            "raw_keys": list(item.raw_payload.keys()),
        },
        raw_payload=item.raw_payload,
        mask=item.mask,
        display_mask=item.display_mask,
        book_date=item.book_date,
        number_type=item.number_type,
        points=item.points,
        date_from=item.date_from,
        operator_fas=item.operator_fas,
        operator_id=item.operator_id,
        last_operation_date=item.last_operation_date,
        manager_id=item.manager_id,
        notes=item.notes,
        abcdef=item.abcdef,
        tariff=item.tariff if purchased else None,
        number_class=item.number_class if purchased else None,
        # Catalog operator is owned by Finenumbers PSTN enrichment (not Runexis).
        operator=None,
        partner=item.partner if purchased else None,
        project=item.project if purchased else None,
        equipment=item.equipment if purchased else None,
    )
