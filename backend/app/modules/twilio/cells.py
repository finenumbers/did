"""Queryable cells for the Twilio number-enrichment stage."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.twilio import TwilioGeo
from app.providers.twilio import contract


@dataclass(frozen=True)
class NumberCell:
    region_filter: str
    locality: str | None
    label: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.region_filter, (self.locality or "").strip().lower())


def is_queryable_geo(row: TwilioGeo) -> bool:
    locality = (row.locality or "").strip()
    region_filter = (row.region_filter or "").strip()
    return bool(locality or region_filter)


def cell_from_geo(row: TwilioGeo) -> NumberCell | None:
    if not is_queryable_geo(row):
        return None
    locality = (row.locality or "").strip() or None
    region_filter = (row.region_filter or "").strip().upper()
    label = locality or region_filter
    return NumberCell(region_filter=region_filter, locality=locality, label=label)


def country_cell() -> NumberCell:
    return NumberCell(region_filter="", locality=None, label="")


def build_number_cells(geo_rows: list[TwilioGeo]) -> list[NumberCell]:
    cells: list[NumberCell] = []
    seen: set[tuple[str, str]] = set()
    for row in geo_rows:
        cell = cell_from_geo(row)
        if cell is None or cell.key in seen:
            continue
        seen.add(cell.key)
        cells.append(cell)
    if not cells:
        return [country_cell()]
    return cells


def should_repeat_contains(
    returned: int,
    new_unique: int,
    cap: int = contract.AVAILABLE_PAGE_CEILING,
) -> bool:
    return returned >= cap and new_unique > 0
