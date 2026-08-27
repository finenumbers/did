"""Twilio region/city classification — no live API, no invented inventory."""

import inspect
import uuid

from app.modules.twilio.geo_classify import classify_geo
from app.modules.twilio.persist import classified_column_updates, needs_geo_finalize
from app.services.twilio_service import TwilioCatalogService, TwilioNumbersService


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


def test_classified_column_updates_match_classify_geo():
    sanday_id = uuid.uuid4()
    england_id = uuid.uuid4()
    us_id = uuid.uuid4()
    yorks_id = uuid.uuid4()
    updates = classified_column_updates(
        [
            (sanday_id, "GB", "United Kingdom", "Sanday", None),
            (england_id, "GB", "United Kingdom", "England", "Leeds"),
            (us_id, "US", "United States", "CA", "Hilo"),
            (yorks_id, "GB", "United Kingdom", "West Yorkshire", "Leeds"),
        ]
    )
    by_id = {row["id"]: row for row in updates}
    assert by_id[sanday_id] == {"id": sanday_id, "region": None, "locality": "Sanday"}
    assert by_id[england_id] == {"id": england_id, "region": "England", "locality": "Leeds"}
    assert by_id[us_id] == {"id": us_id, "region": "California", "locality": "Hilo"}
    assert by_id[yorks_id] == {"id": yorks_id, "region": None, "locality": "Leeds"}
    again = classified_column_updates([(sanday_id, "GB", "United Kingdom", "Sanday", None)])
    assert again == [{"id": sanday_id, "region": None, "locality": "Sanday"}]


def test_list_getters_do_not_rewrite_geo():
    for method in (
        TwilioNumbersService.list_numbers,
        TwilioNumbersService.list_facets,
        TwilioNumbersService.iter_numbers,
        TwilioCatalogService.list_coverage,
    ):
        src = inspect.getsource(method)
        assert "finalize_all_geo" not in src
        assert "needs_geo_finalize" not in src
        assert "_ensure_classified" not in src
        assert "realign_available_number_iso" not in src
    assert not hasattr(TwilioNumbersService, "_ensure_classified")


def test_needs_geo_finalize_is_limit_one():
    captured: list[object] = []

    class _Db:
        def scalar(self, stmt):
            captured.append(stmt)
            return None

    assert needs_geo_finalize(_Db(), provider_id=uuid.uuid4()) is False
    compiled = str(captured[0].compile(compile_kwargs={"literal_binds": False})).lower()
    assert "limit" in compiled
    assert "twilio_available_numbers" in compiled
