"""Wipe-guard unit tests (no DB)."""

from app.modules.sync_engine.safety import fetch_complete_enough, reload_allowed


def test_empty_incoming_with_existing_refuses():
    ok, reason = reload_allowed(previous=1000, incoming=0, kind="free")
    assert ok is False
    assert reason is not None


def test_empty_incoming_and_empty_catalog_refuses():
    ok, reason = reload_allowed(previous=0, incoming=0, kind="free")
    assert ok is False


def test_first_load_allows_any_positive():
    ok, reason = reload_allowed(previous=0, incoming=10, kind="free")
    assert ok is True
    assert reason is None


def test_free_requires_about_90_percent():
    ok, reason = reload_allowed(previous=10_000, incoming=100, kind="free")
    assert ok is False
    assert "min_allowed" in (reason or "")
    ok2, _ = reload_allowed(previous=10_000, incoming=9_500, kind="free")
    assert ok2 is True


def test_small_purchased_half_rule():
    ok, reason = reload_allowed(previous=40, incoming=10, kind="purchased")
    assert ok is False
    ok2, _ = reload_allowed(previous=40, incoming=25, kind="purchased")
    assert ok2 is True


def test_fetch_complete_enough():
    assert fetch_complete_enough(expected=0, fetched=10)[0] is True
    assert fetch_complete_enough(expected=1000, fetched=0)[0] is False
    assert fetch_complete_enough(expected=10_000, fetched=5_000)[0] is False
    assert fetch_complete_enough(expected=10_000, fetched=9_600)[0] is True
