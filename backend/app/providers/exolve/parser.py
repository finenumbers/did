"""Parse Exolve GetList / GetFree payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.exolve import contract
from app.providers.msisdn_split import normalize_phone


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_reference(
    data: dict[str, Any],
) -> tuple[list[ParsedRegion], list[ParsedCity], list[dict[str, Any]]]:
    """Return (all regions, leaf cities, category raw dicts)."""
    regions_raw = data.get("regions") if isinstance(data.get("regions"), list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for row in regions_raw:
        if not isinstance(row, dict):
            continue
        rid = _as_text(row.get("region_id"))
        if rid:
            by_id[rid] = row

    regions: list[ParsedRegion] = []
    cities: list[ParsedCity] = []
    for rid, row in by_id.items():
        name = _as_text(row.get("description")) or _as_text(row.get("region_name"))
        eng = _as_text(row.get("region_name"))
        parent = _as_text(row.get("parent_region_id"))
        regions.append(
            ParsedRegion(
                raw_payload=row,
                region_external_id=rid,
                name=name,
                eng_name=eng,
            )
        )
        # Leaf: has parent different from self (and usually under Russia).
        if parent and parent != rid:
            parent_row = by_id.get(parent) or {}
            parent_name = (
                _as_text(parent_row.get("description"))
                or _as_text(parent_row.get("region_name"))
            )
            cities.append(
                ParsedCity(
                    raw_payload=row,
                    city_external_id=rid,
                    name=name,
                    eng_name=eng,
                    region_external_id=parent,
                    region_name=parent_name,
                )
            )

    categories: list[dict[str, Any]] = []
    for row in data.get("categories") or []:
        if isinstance(row, dict):
            categories.append(row)

    return regions, cities, categories


def parse_number_item(
    item: dict[str, Any],
    *,
    region_id: int | None = None,
) -> ParsedNumberItem:
    phone = normalize_phone(item.get("number_code"))
    region_ext = _as_text(region_id) if region_id is not None else None
    return ParsedNumberItem(
        raw_payload=item,
        provider_number_key=phone,
        msisdn=phone,
        city_external_id=region_ext,
        region_external_id=region_ext,
        city_name=None,
        region_name=_as_text(item.get("region_name")),
        buy_price=_as_decimal(item.get("install_fee")),
        period_price=_as_decimal(item.get("subscription_fee")),
        status_raw=contract.STATUS_FREE,
        number_type=_as_text(item.get("type_name")),
        number_class=_as_text(item.get("category_name")),
    )
