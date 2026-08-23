"""JSON:API helpers + DID Group / SKU mapping for DIDWW API v3."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.providers.didww import contract


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def included_index(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for item in payload.get("included") or []:
        if isinstance(item, dict) and item.get("type") and item.get("id"):
            idx[(str(item["type"]), str(item["id"]))] = item
    return idx


def merge_included(
    base: dict[tuple[str, str], dict[str, Any]],
    extra: dict[tuple[str, str], dict[str, Any]],
) -> None:
    base.update(extra)


def related_one(
    resource: dict[str, Any],
    rel_name: str,
    idx: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    rels = resource.get("relationships") or {}
    data = (rels.get(rel_name) or {}).get("data")
    if not isinstance(data, dict):
        return None
    return idx.get((str(data.get("type")), str(data.get("id"))))


def related_many(
    resource: dict[str, Any],
    rel_name: str,
    idx: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rels = resource.get("relationships") or {}
    data = (rels.get(rel_name) or {}).get("data")
    if data is None:
        return []
    if isinstance(data, dict):
        data = [data]
    out: list[dict[str, Any]] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        found = idx.get((str(item.get("type")), str(item.get("id"))))
        if found:
            out.append(found)
    return out


def collection_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def top_level_meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}


def total_records(payload: dict[str, Any]) -> int | None:
    """Collection size reported by DIDWW: `total_records`, or `total_count` on available_dids."""
    meta = top_level_meta(payload)
    for key in (contract.META_TOTAL_RECORDS, contract.META_TOTAL_COUNT):
        if key in meta:
            value = to_int(meta[key])
            if value is not None:
                return value
    return None


def last_page_number(payload: dict[str, Any]) -> int | None:
    """`page[number]` from `links.last` (DIDWW sends first/last, never next)."""
    links = payload.get("links")
    if not isinstance(links, dict):
        return None
    last = links.get("last")
    if not isinstance(last, str) or not last.strip():
        return None
    raw = (parse_qs(urlparse(last).query).get("page[number]") or [None])[0]
    return to_int(raw)


@dataclass
class SkuRow:
    sku_id: str
    setup_price: Decimal | None
    monthly_price: Decimal | None
    channels_included: int | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DidGroupRow:
    group_id: str
    area_name: str | None
    prefix: str | None
    features: list[str]
    is_metered: bool | None
    allow_additional_channels: bool | None
    service_restrictions: str | None
    is_available: bool | None
    stock_count: int | None
    number_select: bool | None
    needs_registration: bool | None
    country_id: str | None
    country_name: str | None
    country_iso: str | None
    country_prefix: str | None
    region_id: str | None
    region_name: str | None
    city_id: str | None
    city_name: str | None
    did_type: str | None
    skus: list[SkuRow]
    raw: dict[str, Any] = field(default_factory=dict)


def parse_sku(resource: dict[str, Any]) -> SkuRow:
    attrs = resource.get("attributes") or {}
    return SkuRow(
        sku_id=str(resource.get("id") or ""),
        setup_price=to_decimal(attrs.get(contract.SKU_SETUP_PRICE)),
        monthly_price=to_decimal(attrs.get(contract.SKU_MONTHLY_PRICE)),
        channels_included=to_int(attrs.get(contract.SKU_CHANNELS_INCLUDED)),
        raw=resource,
    )


def pick_display_sku(skus: list[SkuRow]) -> SkuRow | None:
    if not skus:
        return None
    zero = [s for s in skus if s.channels_included == 0]
    pool = zero or skus

    def sort_key(s: SkuRow) -> tuple[Decimal, Decimal]:
        monthly = s.monthly_price if s.monthly_price is not None else Decimal("Infinity")
        setup = s.setup_price if s.setup_price is not None else Decimal("Infinity")
        return (monthly, setup)

    return min(pool, key=sort_key)


def parse_country(resource: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not resource:
        return None, None, None
    attrs = resource.get("attributes") or {}
    name = attrs.get(contract.ATTR_NAME)
    iso = attrs.get(contract.ATTR_ISO)
    prefix = attrs.get(contract.ATTR_PREFIX)
    return (
        str(name) if name is not None else None,
        str(iso) if iso is not None else None,
        str(prefix) if prefix is not None else None,
    )


def parse_named(resource: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not resource:
        return None, None
    attrs = resource.get("attributes") or {}
    ident = str(resource.get("id") or "") or None
    name = attrs.get(contract.ATTR_NAME)
    return ident, (str(name) if name is not None else None)


def parse_did_group(resource: dict[str, Any], idx: dict[tuple[str, str], dict[str, Any]]) -> DidGroupRow:
    attrs = resource.get("attributes") or {}
    # Meta attributes live on the primary resource only, they never arrive via includes.
    meta = resource.get("meta") or {}
    features_raw = attrs.get(contract.ATTR_FEATURES) or []
    features = [str(x) for x in features_raw] if isinstance(features_raw, list) else []

    country = related_one(resource, contract.REL_COUNTRY, idx)
    region = related_one(resource, contract.REL_REGION, idx)
    city = related_one(resource, contract.REL_CITY, idx)
    gtype = related_one(resource, contract.REL_DID_GROUP_TYPE, idx)
    sku_resources = related_many(resource, contract.REL_SKUS, idx)

    country_name, country_iso, country_prefix = parse_country(country)
    region_id, region_name = parse_named(region)
    city_id, city_name = parse_named(city)
    _type_id, did_type = parse_named(gtype)
    skus = [parse_sku(s) for s in sku_resources]

    area_name = attrs.get(contract.ATTR_AREA_NAME)
    prefix = attrs.get(contract.ATTR_PREFIX)
    restrictions = attrs.get(contract.ATTR_SERVICE_RESTRICTIONS)
    return DidGroupRow(
        group_id=str(resource.get("id") or ""),
        area_name=str(area_name) if area_name is not None else None,
        prefix=str(prefix) if prefix is not None else None,
        features=features,
        is_metered=to_bool(attrs.get(contract.ATTR_IS_METERED)),
        allow_additional_channels=to_bool(attrs.get(contract.ATTR_ALLOW_ADDITIONAL_CHANNELS)),
        service_restrictions=str(restrictions) if restrictions is not None else None,
        is_available=to_bool(meta.get(contract.META_IS_AVAILABLE)),
        stock_count=to_int(meta.get(contract.META_STOCK_COUNT)),
        number_select=to_bool(meta.get(contract.META_AVAILABLE_DIDS_ENABLED)),
        needs_registration=to_bool(meta.get(contract.META_NEEDS_REGISTRATION)),
        country_id=str(country.get("id")) if country else None,
        country_name=country_name,
        country_iso=country_iso,
        country_prefix=country_prefix,
        region_id=region_id,
        region_name=region_name,
        city_id=city_id,
        city_name=city_name,
        did_type=did_type,
        skus=skus,
        raw=resource,
    )
