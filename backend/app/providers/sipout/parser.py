"""Parse SipOut responses. Formal envelope VERIFIED; item keys EXAMPLE-CONFIRMED."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.enums import FieldVerification
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
                gmt=_as_text(item.get("gmt")),
                field_verification={
                    "region_external_id": FieldVerification.example_confirmed,
                    "name": FieldVerification.example_confirmed,
                },
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
                region_external_id=_as_text(item.get("region_id")),
                field_verification={
                    "city_external_id": FieldVerification.example_confirmed,
                    "name": FieldVerification.example_confirmed,
                    "region_external_id": FieldVerification.example_confirmed,
                },
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


def _parse_has_sms(value: Any) -> bool | None:
    # EXAMPLE-CONFIRMED encoding uncertain — TODO: VERIFY_WITH_DOC_FILE
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"1", "true", "yes"}:
        return True
    if s in {"0", "false", "no"}:
        return False
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
        out.append(
            ParsedNumberItem(
                raw_payload=item,
                provider_number_key=did,
                msisdn=did,  # EXAMPLE-CONFIRMED candidate; not formal E.164 guarantee
                city_external_id=_as_text(item.get("city_id")),
                price_amount=_parse_price(item.get("price")),
                status_raw=_as_text(item.get("status")),
                has_sms=_parse_has_sms(item.get("has_sms")),
                field_verification={
                    "provider_number_key": FieldVerification.example_confirmed,
                    "msisdn": FieldVerification.example_confirmed,
                    "city_external_id": FieldVerification.example_confirmed,
                    "price_amount": FieldVerification.example_confirmed
                    if item.get("price") is not None
                    else FieldVerification.missing,
                    "status_raw": FieldVerification.example_confirmed
                    if item.get("status") is not None
                    else FieldVerification.missing,
                    "has_sms": FieldVerification.example_confirmed
                    if item.get("has_sms") is not None
                    else FieldVerification.missing,
                    "price_currency": FieldVerification.unresolved,
                },
            )
        )
    return out
