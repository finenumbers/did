"""Parse MCN showcase JSON. Docs: mcn-contract.md."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderParseError
from app.providers.msisdn_split import normalize_phone
from app.providers.mcn import contract


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_list_payload(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "result", "items", "countries", "cities", "regions"):
            val = body.get(key)
            if isinstance(val, list):
                return val
        # GetCountriesResponseDto may nest countries
        countries = body.get("countries")
        if isinstance(countries, list):
            return countries
    return []


def parse_regions(body: Any) -> list[ParsedRegion]:
    out: list[ParsedRegion] = []
    for row in extract_list_payload(body):
        if not isinstance(row, dict):
            continue
        rid = row.get("id")
        if rid is None:
            continue
        name = (
            str(row.get("short_name") or row.get("key") or row.get("code") or "").strip()
            or None
        )
        out.append(
            ParsedRegion(
                raw_payload=row,
                region_external_id=str(rid),
                name=name,
                eng_name=str(row.get("key") or "").strip() or None,
            )
        )
    return out


def parse_cities(body: Any) -> list[ParsedCity]:
    out: list[ParsedCity] = []
    for row in extract_list_payload(body):
        if not isinstance(row, dict):
            continue
        cid = row.get("city_id")
        if cid is None:
            continue
        region = row.get("region") if isinstance(row.get("region"), dict) else {}
        rid = region.get("id")
        rname = (
            str(region.get("name") or "").strip()
            or None
        )
        out.append(
            ParsedCity(
                raw_payload=row,
                city_external_id=str(cid),
                name=str(row.get("city_name") or "").strip() or None,
                region_external_id=str(rid) if rid is not None else None,
                region_name=rname,
            )
        )
    return out


def extract_numbers_page(body: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(body, dict):
        raise ProviderParseError("MCN numbers: expected JSON object")
    numbers = body.get("numbers")
    items = [x for x in numbers if isinstance(x, dict)] if isinstance(numbers, list) else []
    total = _as_int(body.get("totalNumbers"))
    return items, total


def _pick_msisdn(item: dict[str, Any]) -> str | None:
    for key in (
        "number",
        "voip_number",
        "common_number_subscriber",
        "number_subscriber",
    ):
        msisdn = normalize_phone(item.get(key))
        if msisdn:
            return msisdn
    # concatenate country_prefix + ndc + subscriber if present
    prefix = "".join(ch for ch in str(item.get("country_prefix") or "") if ch.isdigit())
    ndc = "".join(ch for ch in str(item.get("ndc") or item.get("common_ndc") or "") if ch.isdigit())
    sub = "".join(
        ch
        for ch in str(
            item.get("number_subscriber") or item.get("common_number_subscriber") or ""
        )
        if ch.isdigit()
    )
    if prefix or ndc or sub:
        return normalize_phone(f"{prefix}{ndc}{sub}")
    return None


def parse_number_item(
    item: dict[str, Any],
    *,
    city_name: str | None = None,
    region_name: str | None = None,
) -> ParsedNumberItem:
    msisdn = _pick_msisdn(item)
    city_id = item.get("city_id")
    region_id = item.get("region")
    tariff = item.get("default_tariff") if isinstance(item.get("default_tariff"), dict) else {}
    buy = _as_decimal(tariff.get("price_setup"))
    period = _as_decimal(tariff.get("price_per_period"))
    if period is None:
        period = _as_decimal(item.get("price"))
    ndc_type = item.get("ndc_type_id")
    beauty = item.get("beauty_level")
    return ParsedNumberItem(
        raw_payload=item,
        provider_number_key=msisdn,
        msisdn=msisdn,
        city_external_id=str(city_id) if city_id is not None else None,
        region_external_id=str(region_id) if region_id is not None else None,
        city_name=city_name,
        region_name=region_name,
        buy_price=buy,
        period_price=period,
        status_raw=contract.STATUS_FREE,
        number_type=str(ndc_type) if ndc_type is not None else None,
        number_class=str(beauty) if beauty is not None else None,
    )


def has_ru_country(body: Any) -> bool:
    rows = extract_list_payload(body)
    if isinstance(body, dict) and isinstance(body.get("countries"), list):
        rows = body["countries"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _as_int(row.get("country_code")) == contract.COUNTRY_CODE_RU:
            return True
    return False
