"""Required mask-type directory rows by digit capacity."""

from __future__ import annotations

from decimal import Decimal

from app.modules.catalog.number_category import (
    CATEGORY_GEOGRAPHIC,
    CATEGORY_MOBILE,
    CATEGORY_TOLLFREE,
)

ALLOWED_CATEGORIES = frozenset(
    {CATEGORY_GEOGRAPHIC, CATEGORY_MOBILE, CATEGORY_TOLLFREE}
)

# Same hex as frontend masks-table row fills.
MASK_FILL_MOBILE = "#C6EFCE"
MASK_FILL_TOLLFREE = "#BDD7EE"
MASK_FILL_PREMIUM = "#FFEB9C"

_CAPS_GEOGRAPHIC_ONLY = frozenset({"5", "6"})
_CAP_SEVEN = "7"


def required_categories(digit_capacity: str) -> tuple[str, ...]:
    if digit_capacity == _CAP_SEVEN:
        return (CATEGORY_GEOGRAPHIC, CATEGORY_MOBILE, CATEGORY_TOLLFREE)
    return (CATEGORY_GEOGRAPHIC,)


def is_required_key(*, digit_capacity: str, category: str, abc: str) -> bool:
    return (abc or "") == "" and (category or "") in required_categories(
        digit_capacity or ""
    )


def normalize_import_category(digit_capacity: str, category: str) -> str:
    """Force 5/6 to Городской; empty 7 to Городской; reject unknown 7 names."""
    cap = digit_capacity or ""
    cat = category or ""
    if cap in _CAPS_GEOGRAPHIC_ONLY:
        return CATEGORY_GEOGRAPHIC
    if not cat:
        return CATEGORY_GEOGRAPHIC
    if cat not in ALLOWED_CATEGORIES:
        raise ValueError(f"неизвестная категория {cat}")
    if cap != _CAP_SEVEN and cat != CATEGORY_GEOGRAPHIC:
        return CATEGORY_GEOGRAPHIC
    return cat


def mask_row_fill_color(
    category: str, premium: Decimal | None
) -> str | None:
    if category == CATEGORY_MOBILE:
        return MASK_FILL_MOBILE
    if category == CATEGORY_TOLLFREE:
        return MASK_FILL_TOLLFREE
    if category == CATEGORY_GEOGRAPHIC and premium is not None:
        return MASK_FILL_PREMIUM
    return None
