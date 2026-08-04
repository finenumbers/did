"""Wipe-guard unit tests (no DB)."""

from app.models.enums import InventoryKind, MappingConfidence
from app.modules.sync_engine.safety import count_unique_provider_keys, reload_allowed
from app.providers.dto.numbers import NormalizedNumber


def _num(key: str) -> NormalizedNumber:
    return NormalizedNumber(
        inventory_kind=InventoryKind.free,
        provider_number_key=key,
        msisdn=key,
        city_external_id=None,
        region_external_id=None,
        city_name=None,
        region_name=None,
        buy_price=None,
        period_price=None,
        status_raw=None,
        mapping_confidence=MappingConfidence.medium,
        normalized_payload={},
        raw_payload={},
    )


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


def test_unique_key_count_last_wins_set():
    nums = [_num("79001111111"), _num("79002222222"), _num("79001111111")]
    assert count_unique_provider_keys(nums) == 2


def test_guard_uses_unique_not_raw_length():
    # 10000 raw rows but only 5000 unique keys must refuse vs previous=10000
    previous = 10_000
    unique = 5_000
    ok, reason = reload_allowed(previous=previous, incoming=unique, kind="free")
    assert ok is False
    assert "min_allowed" in (reason or "")
