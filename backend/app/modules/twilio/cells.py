"""Queryable cells and stop rules for the Twilio number-enrichment stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.providers.twilio import contract
from app.providers.twilio.parser import parse_available_number


@dataclass(frozen=True)
class NumberCell:
    region_filter: str
    locality: str | None
    label: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.region_filter, (self.locality or "").strip().lower())


def country_cell() -> NumberCell:
    return NumberCell(region_filter="", locality=None, label="")


def enrich_cells(country_iso: str, number_type: str) -> list[NumberCell]:
    iso = (country_iso or "").strip().upper()
    ntype = (number_type or "").strip()
    if iso in contract.NANP_COUNTRIES and ntype == contract.GEO_NUMBER_TYPE:
        return [
            NumberCell(region_filter=code, locality=None, label=code)
            for code in contract.region_search_keys(iso)
            if code
        ]
    return [country_cell()]


def should_repeat_pattern(
    returned: int,
    no_new_streak: int,
    cap: int = contract.AVAILABLE_PAGE_CEILING,
) -> bool:
    return returned >= cap and no_new_streak < 2


def apply_batch_novelty(
    items: list[dict[str, Any]],
    known_phones: set[str],
    known_regions: set[str],
    known_cities: set[str],
) -> int:
    new_facts = 0
    for item in items:
        parsed = parse_available_number(item)
        if parsed is None:
            continue
        phone = parsed["phone_number"]
        if phone and phone not in known_phones:
            known_phones.add(phone)
            new_facts += 1
        region = (parsed["region"] or "").strip()
        if region and region not in known_regions:
            known_regions.add(region)
            new_facts += 1
        locality = (parsed["locality"] or "").strip()
        if locality and locality not in known_cities:
            known_cities.add(locality)
            new_facts += 1
    return new_facts
