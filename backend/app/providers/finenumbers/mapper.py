"""Map Finenumbers PSTN ranges to catalog numbers."""

from __future__ import annotations

from typing import Any

from app.models.enums import FieldVerification, InventoryKind, MappingConfidence
from app.providers.dto.numbers import NormalizedNumber


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def msisdn_from_abc_local(abc: str, local: int) -> str:
    return f"7{abc}{local:07d}"


def phone_for_lookup(msisdn: str) -> str | None:
    """API expects 10-digit national number (no leading 7)."""
    digits = "".join(ch for ch in msisdn if ch.isdigit())
    if len(digits) == 11 and digits.startswith("7"):
        return digits[1:]
    if len(digits) == 10:
        return digits
    return None


def parse_msisdn_parts(msisdn: str) -> tuple[str, int] | None:
    digits = "".join(ch for ch in msisdn if ch.isdigit())
    if len(digits) == 11 and digits.startswith("7"):
        return digits[1:4], int(digits[4:])
    if len(digits) == 10:
        return digits[:3], int(digits[3:])
    return None


def expand_range_to_numbers(range_row: dict[str, Any]) -> list[NormalizedNumber]:
    abc = _as_text(range_row.get("abc"))
    if not abc:
        return []
    try:
        start = int(range_row["rangeStart"])
        end = int(range_row["rangeEnd"])
    except (KeyError, TypeError, ValueError):
        return []
    if end < start:
        return []

    operator = _as_text(range_row.get("operator"))
    region = _as_text(range_row.get("region"))
    items: list[NormalizedNumber] = []
    for local in range(start, end + 1):
        msisdn = msisdn_from_abc_local(abc, local)
        number_local = f"{local:07d}"
        verification = {
            "msisdn": FieldVerification.documentation_verified.value,
            "abc_code": FieldVerification.documentation_verified.value,
            "number_local": FieldVerification.documentation_verified.value,
            "region_name": FieldVerification.documentation_verified.value
            if region
            else FieldVerification.missing.value,
            "operator": FieldVerification.documentation_verified.value
            if operator
            else FieldVerification.missing.value,
        }
        items.append(
            NormalizedNumber(
                inventory_kind=InventoryKind.free,
                provider_number_key=msisdn,
                msisdn=msisdn,
                city_external_id=None,
                region_external_id=None,
                city_name=None,
                region_name=region,
                buy_price=None,
                period_price=None,
                status_raw=None,
                field_verification=verification,
                mapping_confidence=MappingConfidence.high,
                normalized_payload={
                    "source": "finenumbers_pstn_by_inn",
                    "range_id": range_row.get("id"),
                    "inn": range_row.get("inn"),
                    "capacity": range_row.get("capacity"),
                },
                raw_payload=dict(range_row),
                abc_code=abc,
                number_local=number_local,
                operator=operator,
            )
        )
    return items


def expand_ranges(ranges: list[dict[str, Any]]) -> list[NormalizedNumber]:
    out: list[NormalizedNumber] = []
    for row in ranges:
        out.extend(expand_range_to_numbers(row))
    return out
