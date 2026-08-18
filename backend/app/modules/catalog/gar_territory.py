"""Parse PSTN garTerritory into catalog city_name / region_name."""

from __future__ import annotations

# Longest prefixes first so "город-курорт " is not eaten by "город ", "г.о. " by "г. ".
_PREFIXES = (
    "город-курорт ",
    "Город-курорт ",
    "город-герой ",
    "Город-герой ",
    "г.о. ",
    "город ",
    "Город ",
    "м.р-н ",
    "г. ",
)

_CITY_ALIASES = {
    "Старооскольский": "Старый Оскол",
    "Кемеровский": "Кемерово",
    "Новокузнецкий": "Новокузнецк",
    "Владивостокский": "Владивосток",
    "Майкопский": "Майкоп",
    "Магнитогорский": "Магнитогорск",
    "Миасский": "Миасс",
    "Челябинский": "Челябинск",
    "Волгодонской": "Волгодонск",
}


def strip_gar_prefix(value: str) -> str | None:
    """Strip leading GAR labels (г., город, город-курорт, …) in a loop."""
    text = value.replace("\xa0", " ")
    changed = True
    while text and changed:
        changed = False
        stripped = text.lstrip()
        for prefix in _PREFIXES:
            if stripped.startswith(prefix):
                text = stripped[len(prefix) :]
                changed = True
                break
        else:
            text = stripped
    return text.strip() or None


def normalize_catalog_city(raw: str | None) -> str | None:
    """Strip GAR prefixes and map district adjectives to city names. City column only."""
    if raw is None:
        return None
    if is_coverage_value(raw):
        return None
    cleaned = strip_gar_prefix(raw)
    if not cleaned:
        return None
    return _CITY_ALIASES.get(cleaned, cleaned)


def gar_coverage_tokens(raw: str | None) -> set[str]:
    """Unique comma-separated place names after GAR prefix strip."""
    if raw is None:
        return set()
    out: set[str] = set()
    for chunk in str(raw).replace("\xa0", " ").split(","):
        token = strip_gar_prefix(chunk)
        if token:
            out.add(token.casefold())
    return out


def is_coverage_value(text: str | None) -> bool:
    """True when a field is a subject-coverage list, not a city/region."""
    return len(gar_coverage_tokens(text)) > 2


def _sides(raw: str) -> tuple[str, str | None]:
    """City is before the first pipe; region is after the last. Middle ignored."""
    first = raw.find("|")
    if first < 0:
        return raw, None
    last = raw.rfind("|")
    return raw[:first], raw[last + 1 :]


def gar_clears_geo(raw: str | None) -> bool:
    """True when GAR is a coverage list (empty/missing territory is False)."""
    if raw is None:
        return False
    text = str(raw).replace("\xa0", " ")
    if not text.strip():
        return False
    left, right = _sides(text)
    if right is None:
        return is_coverage_value(left)
    return is_coverage_value(left) or is_coverage_value(right)


def _clean_side(raw: str) -> str | None:
    if is_coverage_value(raw):
        return None
    return strip_gar_prefix(raw)


def parse_gar_territory(raw: str | None) -> tuple[str | None, str | None]:
    """Split Территория ГАР into catalog city_name / region_name.

    No delimiter → city is normalized; region is stripped without the city alias map.
    One or more ``|`` → city is before the first, region is after the last
    (middle segments dropped).
    Leading GAR prefixes are stripped in a loop from each side.
    A comma-list of more than two unique places is not a city/region (None).
    """
    if raw is None:
        return None, None
    text = str(raw).replace("\xa0", " ")
    if not text.strip():
        return None, None
    left, right = _sides(text)
    if right is None:
        return normalize_catalog_city(left), _clean_side(left)
    return normalize_catalog_city(left), _clean_side(right)
