from decimal import Decimal

import pytest

from app.modules.catalog.mask_type_policy import (
    MASK_FILL_MOBILE,
    MASK_FILL_PREMIUM,
    MASK_FILL_TOLLFREE,
    is_required_key,
    mask_row_fill_color,
    normalize_import_category,
    required_categories,
)
from app.modules.catalog.number_category import (
    CATEGORY_GEOGRAPHIC,
    CATEGORY_MOBILE,
    CATEGORY_TOLLFREE,
)


def test_required_categories_by_capacity():
    assert required_categories("5") == (CATEGORY_GEOGRAPHIC,)
    assert required_categories("6") == (CATEGORY_GEOGRAPHIC,)
    assert required_categories("7") == (
        CATEGORY_GEOGRAPHIC,
        CATEGORY_MOBILE,
        CATEGORY_TOLLFREE,
    )


def test_is_required_key_empty_abc_only():
    assert is_required_key(
        digit_capacity="7", category=CATEGORY_MOBILE, abc=""
    )
    assert not is_required_key(
        digit_capacity="7", category=CATEGORY_MOBILE, abc="903"
    )
    assert not is_required_key(digit_capacity="7", category="", abc="")
    assert is_required_key(
        digit_capacity="5", category=CATEGORY_GEOGRAPHIC, abc=""
    )


def test_normalize_five_six_always_geographic():
    assert normalize_import_category("5", CATEGORY_MOBILE) == CATEGORY_GEOGRAPHIC
    assert normalize_import_category("6", "") == CATEGORY_GEOGRAPHIC
    assert normalize_import_category("6", CATEGORY_TOLLFREE) == CATEGORY_GEOGRAPHIC


def test_normalize_seven_empty_becomes_geographic():
    assert normalize_import_category("7", "") == CATEGORY_GEOGRAPHIC
    assert normalize_import_category("7", CATEGORY_MOBILE) == CATEGORY_MOBILE


def test_normalize_seven_unknown_rejected():
    with pytest.raises(ValueError, match="неизвестная категория"):
        normalize_import_category("7", "Бесплатный доступ")


def test_mask_row_fill_priority():
    assert mask_row_fill_color(CATEGORY_MOBILE, Decimal("10")) == MASK_FILL_MOBILE
    assert mask_row_fill_color(CATEGORY_TOLLFREE, Decimal("10")) == MASK_FILL_TOLLFREE
    assert mask_row_fill_color(CATEGORY_GEOGRAPHIC, Decimal("1")) == MASK_FILL_PREMIUM
    assert mask_row_fill_color(CATEGORY_GEOGRAPHIC, None) is None
