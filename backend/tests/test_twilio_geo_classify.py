"""Twilio region/city classification — no live API, no invented inventory."""

from app.modules.twilio.geo_classify import classify_geo


def _gb(**kwargs):
    return classify_geo(country_iso="GB", country_name="United Kingdom", **kwargs)


def test_gb_keeps_nations_and_moves_lone_town():
    assert _gb(region_raw="England", locality_raw="Leeds") == ("England", "Leeds")
    assert _gb(region_raw="Scotland", locality_raw="Edinburgh") == ("Scotland", "Edinburgh")
    assert _gb(region_raw="Sanday", locality_raw=None) == (None, "Sanday")
    assert _gb(region_raw=None, locality_raw=None) == (None, None)


def test_gb_denies_country_label():
    assert _gb(region_raw="United Kingdom", locality_raw="London") == (None, "London")
    assert _gb(region_raw="United Kingdom", locality_raw="") == (None, None)
    assert _gb(region_raw="United Kingdom Proper", locality_raw=None) == (None, None)


def test_gb_swaps_town_in_region_and_nation_in_locality():
    assert _gb(region_raw="Leeds", locality_raw="England") == ("England", "Leeds")


def test_gb_same_nation_twice_is_region_only():
    assert _gb(region_raw="England", locality_raw="England") == ("England", None)


def test_gb_does_not_promote_county_plus_city():
    assert _gb(region_raw="West Yorkshire", locality_raw="Leeds") == (None, "Leeds")


def test_gb_northern_ireland_without_city_stays_region():
    assert _gb(region_raw="Northern Ireland", locality_raw=None) == ("Northern Ireland", None)


def test_classify_is_idempotent_on_raw():
    first = _gb(region_raw="Sanday", locality_raw=None)
    again = classify_geo(
        country_iso="GB",
        country_name="United Kingdom",
        region_raw="Sanday",
        locality_raw=None,
    )
    assert first == again == (None, "Sanday")


def test_us_code_becomes_full_name():
    assert classify_geo(
        country_iso="US",
        country_name="United States",
        region_raw="CA",
        locality_raw="Hilo",
    ) == ("California", "Hilo")
    assert classify_geo(
        country_iso="US",
        country_name="United States",
        region_raw="CA",
        locality_raw=None,
    ) == ("California", None)
    assert classify_geo(
        country_iso="US",
        country_name="United States",
        region_raw="California",
        locality_raw="Oakland",
    ) == ("California", "Oakland")


def test_ca_province_full_name():
    assert classify_geo(
        country_iso="CA",
        country_name="Canada",
        region_raw="ON",
        locality_raw="Toronto",
    ) == ("Ontario", "Toronto")


def test_de_land_stays_region():
    assert classify_geo(
        country_iso="DE",
        country_name="Germany",
        region_raw="Bavaria",
        locality_raw="Munich",
    ) == ("Bavaria", "Munich")
    assert classify_geo(
        country_iso="DE",
        country_name="Germany",
        region_raw="Bayern",
        locality_raw=None,
    ) == ("Bayern", None)
    assert classify_geo(
        country_iso="DE",
        country_name="Germany",
        region_raw="Germany",
        locality_raw="Berlin",
    ) == ("Berlin", None)


def test_fr_region_keep_and_deny_country():
    assert classify_geo(
        country_iso="FR",
        country_name="France",
        region_raw="Île-de-France",
        locality_raw="Paris",
    ) == ("Île-de-France", "Paris")
    assert classify_geo(
        country_iso="FR",
        country_name="France",
        region_raw="France",
        locality_raw=None,
    ) == (None, None)


def test_other_country_trusts_pair_and_moves_lone_region():
    assert classify_geo(
        country_iso="IT",
        country_name="Italy",
        region_raw="Lazio",
        locality_raw="Rome",
    ) == ("Lazio", "Rome")
    assert classify_geo(
        country_iso="IT",
        country_name="Italy",
        region_raw="A village",
        locality_raw=None,
    ) == (None, "A village")
    assert classify_geo(
        country_iso="IT",
        country_name="Italy",
        region_raw="Italy",
        locality_raw="Rome",
    ) == (None, "Rome")
