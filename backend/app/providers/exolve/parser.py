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


def extract_free_numbers(payload: Any) -> list[dict[str, Any]]:
    """Extract NumberElement dicts from a GetFree JSON body (tolerant of wrappers)."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [n for n in payload if isinstance(n, dict)]
    if not isinstance(payload, dict):
        return []

    candidates: list[Any] = [
        payload.get("numbers"),
        payload.get("Numbers"),
    ]
    for wrap_key in ("result", "data", "response", "payload"):
        wrap = payload.get(wrap_key)
        if isinstance(wrap, dict):
            candidates.append(wrap.get("numbers"))
            candidates.append(wrap.get("Numbers"))
        elif isinstance(wrap, list):
            candidates.append(wrap)

    for numbers in candidates:
        if numbers is None:
            continue
        if not isinstance(numbers, list):
            raise TypeError("Exolve GetFree: numbers is not a list")
        return [n for n in numbers if isinstance(n, dict)]
    return []


def summarize_free_payload(raw_status: int, body_json: Any, body_text: str) -> dict[str, Any]:
    """Compact diagnostics for logs / test_connection (no secrets)."""
    keys: list[str] = []
    if isinstance(body_json, dict):
        keys = sorted(str(k) for k in body_json.keys())
    try:
        numbers = extract_free_numbers(body_json)
        extract_error = None
    except TypeError as exc:
        numbers = []
        extract_error = str(exc)
    sample_code = None
    if numbers:
        sample_code = numbers[0].get("number_code")
    return {
        "http_status": raw_status,
        "json_keys": keys,
        "json_parsed": body_json is not None,
        "numbers_len": len(numbers),
        "sample_number_code": sample_code,
        "extract_error": extract_error,
        "body_text_preview": (body_text or "")[:500],
    }


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
