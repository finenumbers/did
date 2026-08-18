from app.modules.catalog.geo_policy import (
    GEO_TOLLFREE,
    catalog_city_region,
    collapse_mobile_capitals,
)
from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY as SENTINEL


def test_absent_wins_over_tollfree_and_mobile():
    assert catalog_city_region(
        "800", "78001234567", "Самара", "Самарская область", pstn_absent=True
    ) == (SENTINEL, SENTINEL)
    assert catalog_city_region(
        "900",
        "79001234567",
        SENTINEL,
        SENTINEL,
    ) == (SENTINEL, SENTINEL)
    assert catalog_city_region(
        "495", "74951234567", None, None, pstn_absent=True
    ) == (SENTINEL, SENTINEL)


def test_found_tollfree_is_russia_even_with_gar_or_empty():
    assert catalog_city_region(
        "800", "78001234567", "Самара", "Самарская область"
    ) == (GEO_TOLLFREE, GEO_TOLLFREE)
    assert catalog_city_region("800", "78001234567", None, None) == (
        GEO_TOLLFREE,
        GEO_TOLLFREE,
    )
    assert catalog_city_region(None, "78009990000", "X", "Y") == (
        GEO_TOLLFREE,
        GEO_TOLLFREE,
    )


def test_mobile_four_capital_pairs():
    assert collapse_mobile_capitals("Московская область", "Город Москва") == (
        "Москва",
        "Москва",
    )
    assert collapse_mobile_capitals(
        "Ленинградская область", "Город Санкт-Петербург"
    ) == ("Санкт-Петербург", "Санкт-Петербург")
    assert collapse_mobile_capitals("Санкт-Петербург", "Ленинградская область") == (
        "Санкт-Петербург",
        "Санкт-Петербург",
    )
    assert collapse_mobile_capitals("Москва", "Московская область") == (
        "Москва",
        "Москва",
    )


def test_mobile_pipe_gar_and_comma_blob():
    assert catalog_city_region("900", "79001234567", "Москва", "Московская область") == (
        "Москва",
        "Москва",
    )
    assert catalog_city_region(
        "900",
        "79001234567",
        "Московская область, Город Москва",
        "Московская область, Город Москва",
    ) == ("Москва", "Москва")
    assert catalog_city_region(
        "900", "79001234567", "г. Москва", "Московская область"
    ) == ("Москва", "Москва")


def test_geographic_moscow_pair_not_collapsed():
    assert catalog_city_region(
        "495", "74951234567", "Москва", "Московская область"
    ) == ("Москва", "Московская область")


def test_oblast_only_not_collapsed():
    assert collapse_mobile_capitals("Московская область", "Московская область") == (
        "Московская область",
        "Московская область",
    )
    assert catalog_city_region(
        "900", "79001234567", "Московская область", "Московская область"
    ) == ("Московская область", "Московская область")
