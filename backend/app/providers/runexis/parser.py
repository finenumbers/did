"""Parse Runexis responses. Envelope/examples from Runexis.html."""

from __future__ import annotations

from typing import Any

from app.models.enums import FieldVerification
from app.providers.dto.common import RawHttpResult
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.errors import ProviderAuthError, ProviderParseError


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _data_list(raw: RawHttpResult) -> list[dict[str, Any]]:
    if raw.status_code == 401:
        raise ProviderAuthError("Runexis unauthorized (401)")
    body = raw.body_json
    if not isinstance(body, dict):
        raise ProviderParseError("Runexis response is not a JSON object")
    if body.get("success") is False:
        raise ProviderParseError(f"Runexis success=false: {body.get('message')}")
    data = body.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        raise ProviderParseError("Runexis data is not a list")
    return [x for x in data if isinstance(x, dict)]


def parse_me(raw: RawHttpResult) -> dict[str, Any]:
    if raw.status_code == 401:
        raise ProviderAuthError("Runexis unauthorized (401)")
    if raw.status_code >= 400:
        raise ProviderParseError(f"Runexis me failed status={raw.status_code}")
    body = raw.body_json
    if not isinstance(body, dict):
        raise ProviderParseError("Runexis me response not JSON object")
    return body


def parse_regions(raw: RawHttpResult) -> list[ParsedRegion]:
    # EXAMPLE-CONFIRMED: id, name
    out: list[ParsedRegion] = []
    for item in _data_list(raw):
        out.append(
            ParsedRegion(
                raw_payload=item,
                region_external_id=_as_text(item.get("id")),
                name=_as_text(item.get("name")),
                field_verification={
                    "region_external_id": FieldVerification.example_confirmed,
                    "name": FieldVerification.example_confirmed,
                },
            )
        )
    return out


def parse_cities(raw: RawHttpResult) -> list[ParsedCity]:
    # EXAMPLE-CONFIRMED: city_id, city_name, region_id, region_name
    out: list[ParsedCity] = []
    for item in _data_list(raw):
        out.append(
            ParsedCity(
                raw_payload=item,
                city_external_id=_as_text(item.get("city_id")),
                name=_as_text(item.get("city_name")),
                region_external_id=_as_text(item.get("region_id")),
                region_name=_as_text(item.get("region_name")),
                field_verification={
                    "city_external_id": FieldVerification.example_confirmed,
                    "name": FieldVerification.example_confirmed,
                    "region_external_id": FieldVerification.example_confirmed,
                    "region_name": FieldVerification.example_confirmed,
                },
            )
        )
    return out
