"""Aurora → NormalizedNumber. See docs/providers/aurora-field-mapping.md."""

from __future__ import annotations

from app.models.enums import InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.msisdn_split import split_from_parts


def map_number(item: ParsedNumberItem) -> NormalizedNumber | None:
    if not item.provider_number_key or not item.msisdn:
        return None
    abc_code, number_local = split_from_parts(msisdn=item.msisdn)
    return NormalizedNumber(
        inventory_kind=InventoryKind.free,
        provider_number_key=item.provider_number_key,
        msisdn=item.msisdn,
        abc_code=abc_code,
        number_local=number_local,
        city_external_id=None,
        region_external_id=None,
        city_name=item.city_name,
        region_name=item.region_name,
        buy_price=None,
        period_price=item.period_price,
        status_raw=None,
        number_type=item.number_type,
        display_mask=item.display_mask,
        mapping_confidence=MappingConfidence.high,
        normalized_payload={
            "provider_number_key": item.provider_number_key,
            "raw_keys": list(item.raw_payload.keys()),
        },
        raw_payload=item.raw_payload,
    )
