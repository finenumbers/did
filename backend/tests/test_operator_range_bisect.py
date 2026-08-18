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


def test_bisect_picks_covering_range():
    cache = OperatorRangeCache()
    cache.add("999", 0, 99, "A")
    cache.add("999", 100, 199, "B")
    cache.finalize()
    assert cache.resolve_parts("999", 50).operator == "A"
    assert cache.resolve_parts("999", 150).operator == "B"
