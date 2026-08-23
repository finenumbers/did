"""JSON:API helpers + DID Group / SKU mapping. Alias-tolerant (object page vs example JSON)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.didww import contract


def first_present(mapping: dict[str, Any] | None, keys: tuple[str, ...]) -> Any:
    if not mapping:
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


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
    rel_names: tuple[str, ...],
    idx: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rels = resource.get("relationships") or {}
    data = None
    for name in rel_names:
        if name in rels:
            data = (rels.get(name) or {}).get("data")
            break
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


@dataclass
class SkuRow:
    sku_id: str
    setup_price: Decimal | None
    monthly_price: Decimal | None
    channels_included: int
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
    channels = to_int(first_present(attrs, contract.SKU_CHANNELS_KEYS)) or 0
    return SkuRow(
        sku_id=str(resource.get("id") or ""),
        setup_price=to_decimal(first_present(attrs, contract.SKU_SETUP_KEYS)),
        monthly_price=to_decimal(first_present(attrs, contract.SKU_MONTHLY_KEYS)),
        channels_included=channels,
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

    return sorted(pool, key=sort_key)[0]


def parse_country(resource: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not resource:
        return None, None, None
    attrs = resource.get("attributes") or {}
    name = attrs.get("name")
    iso = first_present(attrs, contract.COUNTRY_ISO_KEYS)
    prefix = attrs.get("prefix")
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
    name = attrs.get("name")
    return ident, (str(name) if name is not None else None)


def parse_did_group(resource: dict[str, Any], idx: dict[tuple[str, str], dict[str, Any]]) -> DidGroupRow:
    attrs = resource.get("attributes") or {}
    meta = resource.get("meta") or {}
    features_raw = attrs.get("features") or []
    features = [str(x) for x in features_raw] if isinstance(features_raw, list) else []

    country = related_one(resource, "country", idx)
    region = related_one(resource, "region", idx)
    city = related_one(resource, "city", idx)
    gtype = related_one(resource, "did_group_type", idx)
    sku_resources = related_many(resource, contract.SKU_REL_KEYS, idx)
    if not sku_resources:
        sku_resources = [
            item
            for (typ, _iid), item in idx.items()
            if typ in contract.SKU_INCLUDED_TYPES
            and str(item.get("id"))
            in {
                str(d.get("id"))
                for d in (
                    ((resource.get("relationships") or {}).get(rel) or {}).get("data") or []
                    if isinstance(((resource.get("relationships") or {}).get(rel) or {}).get("data"), list)
                    else [((resource.get("relationships") or {}).get(rel) or {}).get("data")]
                    for rel in contract.SKU_REL_KEYS
                )
                if isinstance(d, dict)
            }
        ]

    country_name, country_iso, country_prefix = parse_country(country)
    region_id, region_name = parse_named(region)
    city_id, city_name = parse_named(city)
    _type_id, did_type = parse_named(gtype)
    skus = [parse_sku(s) for s in sku_resources]

    area_name = first_present(attrs, contract.ATTR_AREA_KEYS)
    prefix = attrs.get("prefix")
    return DidGroupRow(
        group_id=str(resource.get("id") or ""),
        area_name=str(area_name) if area_name is not None else None,
        prefix=str(prefix) if prefix is not None else None,
        features=features,
        is_metered=to_bool(first_present(attrs, contract.ATTR_METERED_KEYS)),
        allow_additional_channels=to_bool(first_present(attrs, contract.ATTR_CHANNELS_KEYS)),
        service_restrictions=(
            str(first_present(attrs, contract.ATTR_RESTRICTIONS_KEYS))
            if first_present(attrs, contract.ATTR_RESTRICTIONS_KEYS) is not None
            else None
        ),
        is_available=to_bool(first_present(meta, contract.META_AVAILABLE_KEYS)),
        stock_count=to_int(first_present(meta, contract.META_STOCK_KEYS)),
        number_select=to_bool(first_present(meta, contract.META_PICKER_KEYS)),
        needs_registration=to_bool(first_present(meta, contract.META_KYC_KEYS)),
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
