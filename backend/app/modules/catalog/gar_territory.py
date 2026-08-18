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


def _strip_leading_prefixes(value: str) -> str | None:
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


def parse_gar_territory(raw: str | None) -> tuple[str | None, str | None]:
    """Split Территория ГАР: before first '|' is city, after is region.

    No delimiter → both fields get the same cleaned value.
    Leading GAR prefixes are stripped in a loop from each side.
    """
    if raw is None:
        return None, None
    text = str(raw).replace("\xa0", " ")
    if not text.strip():
        return None, None
    if "|" in text:
        left, right = text.split("|", 1)
        return _strip_leading_prefixes(left), _strip_leading_prefixes(right)
    cleaned = _strip_leading_prefixes(text)
    return cleaned, cleaned
