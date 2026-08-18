from app.modules.catalog.geographic_from_regions import (
    RegionAbcRow,
    is_geographic_msisdn,
    match_geographic_abc,
)


def _dir(*rows: RegionAbcRow) -> dict[str, RegionAbcRow]:
    return {row.abc: row for row in rows}


def test_is_geographic_msisdn():
    assert is_geographic_msisdn("74997777777")
    assert is_geographic_msisdn("73842666666")
    assert is_geographic_msisdn("78011234567")
    assert not is_geographic_msisdn("79001234567")
    assert not is_geographic_msisdn("78001234567")
    assert not is_geographic_msisdn("84997777777")
    assert not is_geographic_msisdn(None)


def test_match_499_capacity_7():
    directory = _dir(
        RegionAbcRow("499", 7, "Москва", "Москва"),
    )
    assert match_geographic_abc("74997777777", directory) == (
        "499",
        "7777777",
        "Москва",
        "Москва",
    )


def test_match_3842_capacity_6():
    directory = _dir(
        RegionAbcRow("3842", 6, "Новокузнецк", "Кемеровская область"),
    )
    assert match_geographic_abc("73842666666", directory) == (
        "3842",
        "666666",
        "Новокузнецк",
        "Кемеровская область",
    )


def test_match_5_digit_abc():
    directory = _dir(
        RegionAbcRow("35191", 5, "Миасс", "Челябинская область"),
    )
    assert match_geographic_abc("73519112345", directory) == (
        "35191",
        "12345",
        "Миасс",
        "Челябинская область",
    )


def test_longest_prefix_wins():
    directory = _dir(
        RegionAbcRow("384", 7, "Кемерово", "Кемеровская область"),
        RegionAbcRow("3842", 6, "Новокузнецк", "Кемеровская область"),
    )
    assert match_geographic_abc("73842666666", directory) == (
        "3842",
        "666666",
        "Новокузнецк",
        "Кемеровская область",
    )


def test_no_directory_hit_resets_to_3_plus_7():
    assert match_geographic_abc("74951234567", {}) == ("495", "1234567", None, None)


def test_invalid_capacity_row_ignored():
    directory = _dir(
        RegionAbcRow("3842", 7, "Плохой", "Инвариант"),
    )
    assert match_geographic_abc("73842666666", directory) == ("384", "2666666", None, None)


def test_mobile_and_tollfree_untouched():
    directory = _dir(
        RegionAbcRow("900", 7, "Нельзя", "Нельзя"),
        RegionAbcRow("800", 7, "Нельзя", "Нельзя"),
    )
    assert match_geographic_abc("79001234567", directory) is None
    assert match_geographic_abc("78001234567", directory) is None
