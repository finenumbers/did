"""Parse PSTN garTerritory into catalog city_name / region_name."""

from __future__ import annotations

# Longest prefixes first so "г.о. " is not eaten by "г. ".
_PREFIXES = (
    "г.о. ",
    "город ",
    "Город ",
    "м.р-н ",
    "г. ",
)


def strip_gar_prefix(value: str) -> str | None:
    """Strip leading GAR labels (г., город, г.о., …) in a loop."""
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
    first = raw.find("|")
    if first < 0:
        return raw, None
    second = raw.find("|", first + 1)
    left = raw[:first]
    right = raw[first + 1 :] if second < 0 else raw[second + 1 :]
    return left, right


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

    No delimiter → both fields get the same cleaned value.
    One ``|`` → before is city, after is region.
    Two or more ``|`` → city is before the first, region is after the second
    (middle dropped; tail after the second pipe is kept).
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
        cleaned = _clean_side(left)
        return cleaned, cleaned
    return _clean_side(left), _clean_side(right)
