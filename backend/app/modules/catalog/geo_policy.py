"""Catalog city/region after PSTN enrich: sentinel, toll-free РФ, mobile capitals."""

from __future__ import annotations

from app.modules.catalog.gar_territory import (
    is_coverage_value,
    normalize_catalog_city,
    strip_gar_prefix,
)
from app.modules.catalog.number_category import (
    CATEGORY_MOBILE,
    CATEGORY_TOLLFREE,
    classify_number_category,
)
from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY

GEO_TOLLFREE = "Российская Федерация"

_MOSCOW_PAIR = frozenset({"москва", "московская область"})
_SPB_PAIR = frozenset({"санкт-петербург", "ленинградская область"})
_MOSCOW = "Москва"
_SPB = "Санкт-Петербург"


def _norm_token(raw: str) -> str | None:
    collapsed = " ".join(raw.replace("\xa0", " ").split())
    stripped = strip_gar_prefix(collapsed)
    if not stripped:
        return None
    return stripped.casefold()


def _tokens(*parts: str | None) -> set[str]:
    out: set[str] = set()
    for part in parts:
        if not part:
            continue
        for chunk in str(part).split(","):
            token = _norm_token(chunk)
            if token:
                out.add(token)
    return out


def collapse_mobile_capitals(
    city: str | None, region: str | None
) -> tuple[str | None, str | None]:
    tokens = _tokens(city, region)
    if tokens == _MOSCOW_PAIR:
        return _MOSCOW, _MOSCOW
    if tokens == _SPB_PAIR:
        return _SPB, _SPB
    return city, region


def catalog_city_region(
    abc_code: str | None,
    msisdn: str | None,
    city: str | None,
    region: str | None,
    *,
    pstn_absent: bool = False,
) -> tuple[str | None, str | None]:
    """Return catalog city/region. Sentinel always wins over category overlays."""
    if (
        pstn_absent
        or city == OPERATOR_NOT_IN_REGISTRY
        or region == OPERATOR_NOT_IN_REGISTRY
    ):
        return OPERATOR_NOT_IN_REGISTRY, OPERATOR_NOT_IN_REGISTRY
    category = classify_number_category(abc_code, msisdn)
    if category == CATEGORY_TOLLFREE:
        return GEO_TOLLFREE, GEO_TOLLFREE
    if is_coverage_value(city):
        city = None
    if is_coverage_value(region):
        region = None
    city = normalize_catalog_city(city)
    if category == CATEGORY_MOBILE:
        return collapse_mobile_capitals(city, region)
    return city, region
