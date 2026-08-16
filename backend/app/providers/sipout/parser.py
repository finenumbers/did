"""Parse SipOut responses. Formal envelope VERIFIED; item keys EXAMPLE-CONFIRMED."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.dto.common import RawHttpResult
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderAuthError, ProviderParseError


def _require_ok(raw: RawHttpResult) -> dict[str, Any]:
    data = raw.body_json
    if not isinstance(data, dict):
        raise ProviderParseError("SipOut response is not a JSON object")
    result = data.get("result")
    # VERIFIED: result ok|bad
    if result == "bad":
        err = data.get("err")
        err_text = data.get("err_text")
        msg = f"SipOut result=bad err={err} err_text={err_text}"
        if err and "key" in str(err).lower():
            raise ProviderAuthError(msg)
        raise ProviderParseError(msg)
    if result != "ok":
        raise ProviderParseError(f"Unexpected SipOut result value: {result!r}")
    return data


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def parse_balance(raw: RawHttpResult) -> dict[str, Any]:
    return _require_ok(raw)


def parse_geo(raw: RawHttpResult) -> tuple[list[ParsedRegion], list[ParsedCity]]:
    payload = _require_ok(raw)
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise ProviderParseError("SipOut get_cities data is not an object")
    # VERIFIED formal: cities, regions
    regions_raw = data.get("regions") or []
    cities_raw = data.get("cities") or []
    regions: list[ParsedRegion] = []
    for item in regions_raw:
        if not isinstance(item, dict):
            continue
        # EXAMPLE-CONFIRMED keys
        regions.append(
            ParsedRegion(
                raw_payload=item,
                region_external_id=_as_text(item.get("id")),
                name=_as_text(item.get("name")),
                eng_name=_as_text(item.get("eng_name")),
                capital_city=_as_text(item.get("capital_city")),
                gmt=_as_text(item.get("gmt"))
            )
        )
    cities: list[ParsedCity] = []
    for item in cities_raw:
        if not isinstance(item, dict):
            continue
        cities.append(
            ParsedCity(
                raw_payload=item,
                city_external_id=_as_text(item.get("id")),
                name=_as_text(item.get("name")),
                eng_name=_as_text(item.get("eng_name")),
                region_external_id=_as_text(item.get("region_id"))
            )
        )
    return regions, cities


def _parse_price(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_number_list(raw: RawHttpResult) -> list[ParsedNumberItem]:
    payload = _require_ok(raw)
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise ProviderParseError("SipOut number list data is not an object")
    # VERIFIED formal: list
    items = data.get("list") or []
    out: list[ParsedNumberItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        did = _as_text(item.get("did"))
        order_id = _as_text(item.get("order_id"))
        doc_status = _as_text(item.get("doc_status"))
        doc_required = _as_text(item.get("doc_required"))
        order_doc_required = _as_text(item.get("order_doc_required"))
        sign_raw = item.get("sign")
        if sign_raw is None:
            sign = None
        elif isinstance(sign_raw, bool):
            sign = "true" if sign_raw else "false"
        else:
            sign = _as_text(sign_raw)
        out.append(
            ParsedNumberItem(
                raw_payload=item,
                provider_number_key=did,
                msisdn=did,  # EXAMPLE-CONFIRMED candidate; not formal E.164 guarantee
                city_external_id=_as_text(item.get("city_id")),
                # Locked: SipOut free `price` → catalog period_price (not buy_price)
                period_price=_parse_price(item.get("price")),
                buy_price=None,
                status_raw=_as_text(item.get("status")),
                order_id=order_id,
                doc_status=doc_status,
                doc_required=doc_required,
                order_doc_required=order_doc_required,
                sign=sign
            )
        )
    return out
