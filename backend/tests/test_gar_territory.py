from app.modules.catalog.gar_territory import (
    gar_clears_geo,
    is_coverage_value,
    normalize_catalog_city,
    parse_gar_territory,
)

NATIONWIDE = (
    "Республика Адыгея, Республика Башкортостан, Республика Бурятия, "
    "Республика Алтай, Республика Дагестан, Город Байконур, Херсонская область"
)

CITY_ALIASES = (
    ("Старооскольский", "Старый Оскол"),
    ("Кемеровский", "Кемерово"),
    ("Новокузнецкий", "Новокузнецк"),
    ("Владивостокский", "Владивосток"),
    ("Майкопский", "Майкоп"),
    ("Магнитогорский", "Магнитогорск"),
    ("Миасский", "Миасс"),
    ("Челябинский", "Челябинск"),
    ("Волгодонской", "Волгодонск"),
)


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


def test_two_pipes_drops_middle():
    assert parse_gar_territory("г. Самара|середина|Самарская область") == (
        "Самара",
        "Самарская область",
    )
    assert parse_gar_territory("A|B|C|D") == ("A", "D")
    assert parse_gar_territory("A||C") == ("A", "C")


def test_two_token_comma_is_not_coverage():
    assert is_coverage_value("Республика Крым, Город Севастополь") is False
    assert parse_gar_territory("Республика Крым, Город Севастополь") == (
        "Республика Крым, Город Севастополь",
        "Республика Крым, Город Севастополь",
    )
    assert gar_clears_geo("Республика Крым, Город Севастополь") is False
    assert gar_clears_geo("г. Москва") is False
    assert gar_clears_geo(None) is False
    assert gar_clears_geo("") is False


def test_nationwide_comma_list_is_not_a_city():
    assert is_coverage_value(NATIONWIDE) is True
    assert parse_gar_territory(NATIONWIDE) == (None, None)
    assert gar_clears_geo(NATIONWIDE) is True


def test_pipe_with_coverage_region_clears_only_region():
    raw = f"г. Майкоп|{NATIONWIDE}"
    assert parse_gar_territory(raw) == ("Майкоп", None)
    assert gar_clears_geo(raw) is True


def test_honorary_city_prefixes():
    assert parse_gar_territory("город-курорт Сочи|Краснодарский край") == (
        "Сочи",
        "Краснодарский край",
    )
    assert parse_gar_territory("Город-герой\xa0Волгоград|Волгоградская область") == (
        "Волгоград",
        "Волгоградская область",
    )
    assert parse_gar_territory("город-курорт Сочи") == ("Сочи", "Сочи")


def test_city_alias_map_all_pairs():
    for src, dst in CITY_ALIASES:
        assert normalize_catalog_city(src) == dst
        assert parse_gar_territory(f"{src}|Область") == (dst, "Область")


def test_city_alias_does_not_change_region():
    assert parse_gar_territory("Кемеровский") == ("Кемерово", "Кемеровский")
    assert parse_gar_territory("г. Кемеровский|Кемеровская область") == (
        "Кемерово",
        "Кемеровская область",
    )
