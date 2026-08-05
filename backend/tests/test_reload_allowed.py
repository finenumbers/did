"""Wipe-guard unit tests (no DB)."""

from app.models.enums import InventoryKind, MappingConfidence
from app.modules.sync_engine.safety import (
    build_inventory_summary,
    count_unique_provider_keys,
    reload_allowed,
)
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


def test_shrink_or_grow_always_allowed_when_positive():
    ok, reason = reload_allowed(previous=10_000, incoming=100, kind="free")
    assert ok is True
    assert reason is None
    ok2, _ = reload_allowed(previous=10_000, incoming=9_500, kind="free")
    assert ok2 is True
    ok3, _ = reload_allowed(previous=52714, incoming=31771, kind="free")
    assert ok3 is True


def test_purchased_shrink_allowed_when_positive():
    ok, reason = reload_allowed(previous=40, incoming=10, kind="purchased")
    assert ok is True
    assert reason is None


def test_unique_key_count_last_wins_set():
    nums = [_num("79001111111"), _num("79002222222"), _num("79001111111")]
    assert count_unique_provider_keys(nums) == 2


def test_build_inventory_summary_was_became():
    rows = build_inventory_summary(
        {
            "aurora": {
                "free_numbers": {"previous": 52714, "upserted": 31771, "fetched": 37372},
            },
            "sipout": {
                "free_numbers": {"previous": 100, "upserted": 120},
                "purchased_numbers": {"previous": 10, "upserted": 8},
            },
            "operator_enrichment": {"updated": 1},
        }
    )
    by_label = {r["label"]: r for r in rows}
    assert by_label["Aurora Telecom · свободные"]["delta"] == 31771 - 52714
    assert by_label["SipOut · свободные"]["current"] == 120
    assert by_label["SipOut · купленные"]["delta"] == -2
    assert len(rows) == 3
