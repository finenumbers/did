"""
Runexis mapper — geo only for catalog sync.
Free/purchased inventory mapping is NOT implemented (docs insufficient).
TODO: VERIFY_WITH_DOC_FILE — E.164 assembly, free/purchased endpoint mapping, currency
"""

from app.providers.dto.geo import ParsedCity, ParsedRegion


def map_region(item: ParsedRegion) -> ParsedRegion:
    return item


def map_city(item: ParsedCity) -> ParsedCity:
    return item
