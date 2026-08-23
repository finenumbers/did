"""Parse Twilio AvailablePhoneNumbers + Pricing payloads. No fixtures, no invented rows."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.twilio import contract


@dataclass(frozen=True)
class CountryRow:
    country_name: str | None
    country_iso: str
    country_beta: bool
    types: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class PriceRow:
    current_price: Decimal | None
    base_price: Decimal | None
    price_unit: str | None


@dataclass(frozen=True)
class CatalogRow:
    country_name: str | None
    country_iso: str
    number_type: str
    country_beta: bool
    period_price: Decimal | None
    price_unit: str | None
    raw_country: dict[str, Any]
    raw_pricing: dict[str, Any] | None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def search_types(subresource_uris: Any) -> tuple[str, ...]:
    if not isinstance(subresource_uris, dict):
        return ()
    found = [key for key in contract.SEARCH_TYPE_PATHS if key in subresource_uris]
    return tuple(found)


def parse_country(item: dict[str, Any]) -> CountryRow | None:
    iso = str(item.get("country_code") or "").strip().upper()
    if not iso:
        return None
    return CountryRow(
        country_name=str(item.get("country") or "").strip() or None,
        country_iso=iso,
        country_beta=bool(item.get("beta")),
        types=search_types(item.get(contract.SUBRESOURCE_URIS)),
        raw=item,
    )


def parse_pricing(payload: dict[str, Any]) -> dict[str, PriceRow]:
    if not payload.get("iso_country") and not payload.get("phone_number_prices"):
        return {}
    unit = str(payload.get("price_unit") or "").strip() or None
    out: dict[str, PriceRow] = {}
    for entry in payload.get("phone_number_prices") or []:
        if not isinstance(entry, dict):
            continue
        number_type = str(entry.get("number_type") or "").strip()
        if not number_type:
            continue
        out[number_type] = PriceRow(
            current_price=_as_decimal(entry.get("current_price")),
            base_price=_as_decimal(entry.get("base_price")),
            price_unit=unit,
        )
    return out


def price_for_type(prices: dict[str, PriceRow], number_type: str) -> PriceRow | None:
    mapped = contract.PRICING_TYPE_MAP.get(number_type)
    if not mapped:
        return None
    return prices.get(mapped)


def build_catalog_rows(
    countries: list[CountryRow],
    pricing_by_iso: dict[str, dict[str, Any]],
) -> list[CatalogRow]:
    rows: list[CatalogRow] = []
    for country in countries:
        payload = pricing_by_iso.get(country.country_iso)
        prices = parse_pricing(payload) if payload else {}
        for number_type in country.types:
            priced = price_for_type(prices, number_type)
            rows.append(
                CatalogRow(
                    country_name=country.country_name,
                    country_iso=country.country_iso,
                    number_type=number_type,
                    country_beta=country.country_beta,
                    period_price=priced.current_price if priced else None,
                    price_unit=priced.price_unit if priced else None,
                    raw_country=country.raw,
                    raw_pricing=payload,
                )
            )
    return rows


def catalog_key(country_iso: str, number_type: str) -> str:
    return f"{country_iso}:{number_type}"
