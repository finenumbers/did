from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedRegion:
    raw_payload: dict[str, Any]
    region_external_id: str | None = None
    name: str | None = None
    eng_name: str | None = None
    capital_city: str | None = None
    gmt: str | None = None


@dataclass
class ParsedCity:
    raw_payload: dict[str, Any]
    city_external_id: str | None = None
    name: str | None = None
    eng_name: str | None = None
    region_external_id: str | None = None
    region_name: str | None = None
