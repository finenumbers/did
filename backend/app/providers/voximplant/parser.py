"""Parse Voximplant Management API JSON. Docs: voximplant-contract.md."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderAuthError, ProviderError, ProviderParseError
from app.providers.msisdn_split import normalize_phone
from app.providers.voximplant import contract


def raise_for_api_error(body: Any, *, context: str = "") -> None:
    if not isinstance(body, dict):
        return
    err = body.get("error")
    if err is None:
        return
    if isinstance(err, dict):
        code = err.get("code")
        msg = err.get("msg") or err.get("message") or str(err)
    else:
        code = None
        msg = str(err)
    text = f"Voximplant API error{(' ' + context) if context else ''}: {msg}"
    details = {"api_error": err, "context": context}
    if code in (100,):
        raise ProviderAuthError(text, details=details)
    raise ProviderError(text, code=f"VOXIMPLANT_API_{code or 'ERROR'}", details=details)


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def extract_ru_categories(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Return listable RU category dicts with phone_category_name."""
    raise_for_api_error(body, context="GetPhoneNumberCategories")
    result = body.get("result")
    if not isinstance(result, list):
        return []
    out: list[dict[str, Any]] = []
    for country in result:
        if not isinstance(country, dict):
            continue
        cc = str(country.get("country_code") or "").upper()
        if cc != contract.COUNTRY_CODE_RU:
            continue
        if country.get("can_list_phone_numbers") is False:
            continue
        cats = country.get("phone_categories")
        if not isinstance(cats, list):
            continue
        for cat in cats:
            if not isinstance(cat, dict):
                continue
            name = cat.get("phone_category_name")
            if not name:
                continue
            row = dict(cat)
            row["country_code"] = contract.COUNTRY_CODE_RU
            row["phone_category_name"] = str(name).strip()
            out.append(row)
    return out


def extract_regions(body: dict[str, Any], *, category: str) -> list[dict[str, Any]]:
    raise_for_api_error(body, context=f"GetPhoneNumberRegions:{category}")
    result = body.get("result")
    if not isinstance(result, list):
        return []
    out: list[dict[str, Any]] = []
    for row in result:
        if not isinstance(row, dict):
            continue
        rid = row.get("phone_region_id")
        if rid is None:
            continue
        item = dict(row)
        item["_phone_category_name"] = category
        out.append(item)
    return out


def parse_region_city(
    row: dict[str, Any], *, category: str
) -> tuple[ParsedRegion, ParsedCity]:
    rid = str(row.get("phone_region_id"))
    # Composite key: same region id can appear under multiple categories.
    external = f"{category}:{rid}"
    name = (
        str(row.get("localized_phone_region_name") or row.get("phone_region_name") or "").strip()
        or None
    )
    eng = str(row.get("phone_region_name") or "").strip() or None
    code = (
        str(row.get("phone_region_code")).strip()
        if row.get("phone_region_code") is not None
        else None
    )
    region = ParsedRegion(
        raw_payload={**row, "phone_category_name": category, "region_code": code},
        region_external_id=external,
        name=name,
        eng_name=eng,
    )
    city = ParsedCity(
        raw_payload={**row, "phone_category_name": category},
        city_external_id=external,
        name=name,
        eng_name=eng,
        region_external_id=external,
        region_name=name,
    )
    return region, city


def extract_new_phones_page(body: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None, int]:
    """Return (items, total_count|None, returned_count)."""
    raise_for_api_error(body, context="GetNewPhoneNumbers")
    result = body.get("result")
    items = [x for x in result if isinstance(x, dict)] if isinstance(result, list) else []
    total = body.get("total_count")
    total_i = int(total) if total is not None and str(total).isdigit() else None
    count = body.get("count")
    if count is not None:
        try:
            returned = int(count)
        except (TypeError, ValueError):
            returned = len(items)
    else:
        returned = len(items)
    return items, total_i, returned


def parse_number_item(
    item: dict[str, Any],
    *,
    category: str,
    region_id: int,
    region_name: str | None = None,
) -> ParsedNumberItem:
    phone = item.get("phone_number")
    msisdn = normalize_phone(phone)
    external = f"{category}:{region_id}"
    rname = (
        str(item.get("phone_region_name") or region_name or "").strip() or None
    )
    cat = (
        str(item.get("phone_category_name") or category or "").strip() or None
    )
    return ParsedNumberItem(
        raw_payload=item if isinstance(item, dict) else {},
        provider_number_key=msisdn,
        msisdn=msisdn,
        city_external_id=external,
        region_external_id=external,
        city_name=rname,
        region_name=rname,
        buy_price=_as_decimal(item.get("phone_installation_price")),
        period_price=_as_decimal(item.get("phone_price")),
        status_raw=contract.STATUS_FREE,
        number_type=cat,
        number_class=cat,
    )


def require_mapping_body(body: Any, *, method: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ProviderParseError(f"Voximplant {method}: expected JSON object")
    raise_for_api_error(body, context=method)
    return body
