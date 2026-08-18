from app.modules.catalog.gar_territory import parse_gar_territory


def test_pipe_city_and_region():
    assert parse_gar_territory("г. Самара|Самарская область") == (
        "Самара",
        "Самарская область",
    )


def test_nested_prefixes_from_live_gar():
    assert parse_gar_territory("г.о. город Екатеринбург|Свердловская область") == (
        "Екатеринбург",
        "Свердловская область",
    )


def test_no_pipe_fills_both():
    assert parse_gar_territory("г. Москва") == ("Москва", "Москва")
    assert parse_gar_territory("м.р-н Никольский") == ("Никольский", "Никольский")


def test_go_prefix_before_g():
    assert parse_gar_territory("г.о. Химки|Московская область") == ("Химки", "Московская область")


def test_nbsp_and_blank():
    assert parse_gar_territory("г.\xa0Москва") == ("Москва", "Москва")
    assert parse_gar_territory(None) == (None, None)
    assert parse_gar_territory("  ") == (None, None)
    assert parse_gar_territory("г. ") == (None, None)
