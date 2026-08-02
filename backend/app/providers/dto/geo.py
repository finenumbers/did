from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import FieldVerification


@dataclass
class ParsedRegion:
    raw_payload: dict[str, Any]
    region_external_id: str | None = None
    name: str | None = None
    eng_name: str | None = None
    capital_city: str | None = None
    gmt: str | None = None
    field_verification: dict[str, FieldVerification] = field(default_factory=dict)


@dataclass
class ParsedCity:
    raw_payload: dict[str, Any]
    city_external_id: str | None = None
    name: str | None = None
    eng_name: str | None = None
    region_external_id: str | None = None
    region_name: str | None = None
    field_verification: dict[str, FieldVerification] = field(default_factory=dict)
