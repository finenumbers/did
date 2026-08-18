"""OperatorRangeCache bisect must match linear first-insert semantics."""

from __future__ import annotations

from app.providers.finenumbers.enrich import OperatorRangeCache


def test_bisect_matches_linear_first_match_with_overlap():
    cache = OperatorRangeCache()
    # First inserted covers 0-999 → MegaFon
    cache.add("495", 0, 999, "MegaFon")
    # Later overlapping wider range → MTS (must NOT win for local=100)
    cache.add("495", 0, 5000, "MTS")
    cache.finalize()

    msisdn = "74950000100"
    assert cache.resolve_linear_first_match(msisdn).operator == "MegaFon"
    assert cache.resolve(msisdn).operator == "MegaFon"
    assert cache.resolve_parts("495", 100).operator == "MegaFon"


def test_bisect_outside_range_is_none():
    cache = OperatorRangeCache()
    cache.add("495", 1000, 1999, "Beeline")
    cache.finalize()
    assert cache.resolve_parts("495", 500) is None
    assert cache.resolve("74950000500") is None


def test_add_merges_geo_on_duplicate_range_keeps_first_operator():
    cache = OperatorRangeCache()
    cache.add("495", 0, 999, "MegaFon")
    cache.add("495", 0, 999, "MTS", city_name="Москва", region_name="Москва")
    cache.finalize()
    match = cache.resolve_parts("495", 100)
    assert match is not None
    assert match.operator == "MegaFon"
    assert match.city_name == "Москва"
    assert match.region_name == "Москва"


def test_add_does_not_overwrite_existing_geo():
    cache = OperatorRangeCache()
    cache.add("495", 0, 999, "MegaFon", city_name="Химки", region_name="МО")
    cache.add("495", 0, 999, "MTS", city_name="Москва", region_name="Москва")
    cache.finalize()
    match = cache.resolve_parts("495", 100)
    assert match is not None
    assert match.operator == "MegaFon"
    assert match.city_name == "Химки"
    assert match.region_name == "МО"


def test_bisect_picks_covering_range():
    cache = OperatorRangeCache()
    cache.add("999", 0, 99, "A")
    cache.add("999", 100, 199, "B")
    cache.finalize()
    assert cache.resolve_parts("999", 50).operator == "A"
    assert cache.resolve_parts("999", 150).operator == "B"
