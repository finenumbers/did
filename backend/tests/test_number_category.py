from app.modules.catalog.number_category import (
    CATEGORY_GEOGRAPHIC,
    CATEGORY_MOBILE,
    CATEGORY_TOLLFREE,
    classify_number_category,
)


def test_mobile_abc_starts_with_9():
    assert classify_number_category("903") == CATEGORY_MOBILE
    assert classify_number_category("900") == CATEGORY_MOBILE
    assert classify_number_category("999") == CATEGORY_MOBILE


def test_tollfree_800():
    assert classify_number_category("800") == CATEGORY_TOLLFREE


def test_geographic_other_abc():
    assert classify_number_category("495") == CATEGORY_GEOGRAPHIC
    assert classify_number_category("812") == CATEGORY_GEOGRAPHIC
    assert classify_number_category("801") == CATEGORY_GEOGRAPHIC


def test_from_msisdn_when_abc_missing():
    assert classify_number_category(None, "79031234567") == CATEGORY_MOBILE
    assert classify_number_category("", "78001234567") == CATEGORY_TOLLFREE
    assert classify_number_category(None, "74951234567") == CATEGORY_GEOGRAPHIC


def test_missing_abc_and_msisdn():
    assert classify_number_category(None) is None
    assert classify_number_category("") is None
    assert classify_number_category(None, "123") is None
