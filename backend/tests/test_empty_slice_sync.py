"""Empty inventory slice must not cancel the sibling slice."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from app.models.enums import InventoryKind, MappingConfidence, ProviderCode
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.service import SyncService
from app.providers.dto.common import ConnectionConfig, SyncResult
from app.providers.dto.numbers import NormalizedNumber


def _number(key: str) -> NormalizedNumber:
    return NormalizedNumber(
        inventory_kind=InventoryKind.purchased,
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
        raw_payload={"virtual_phone_number": key},
    )


class _Adapter:
    def __init__(self, free: SyncResult, purchased: SyncResult):
        self.free = free
        self.purchased = purchased
        self.calls: list[str] = []

    def capabilities(self) -> dict:
        return {
            "dictionaries": {"supported": False},
            "free_numbers": {"supported": True},
            "purchased_numbers": {"supported": True},
        }

    async def sync_free_numbers(self, connection, **kwargs):
        self.calls.append("free")
        return self.free

    async def sync_purchased_numbers(self, connection, **kwargs):
        self.calls.append("purchased")
        return self.purchased


def _run(monkeypatch, *, free: SyncResult, purchased: SyncResult, previous: list[int]):
    monkeypatch.setattr(
        "app.modules.sync_engine.service.build_city_lookup",
        lambda db, code: {},
    )
    monkeypatch.setattr(
        "app.modules.sync_engine.service.count_present_numbers",
        lambda *args, **kwargs: previous.pop(0),
    )
    monkeypatch.setattr("app.modules.sync_engine.service.log_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.modules.sync_engine.service.record_number_drops",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.modules.sync_engine.service.preserve_operators_on_numbers",
        lambda *args, **kwargs: 0,
    )
    persisted: list[str] = []

    def _persist(*args, **kwargs):
        persisted.append(kwargs["inventory_kind"].value)
        return {"upserted": 1}

    monkeypatch.setattr(
        "app.modules.sync_engine.service.persist_novofon_numbers",
        _persist,
    )
    monkeypatch.setattr(
        "app.modules.sync_engine.service._throttled_persist_progress",
        lambda *args, **kwargs: (lambda *a, **k: None),
    )
    events: list[tuple[str, str, str]] = []

    async def _hook(phase, event, detail="", **kwargs):
        events.append((phase, event, detail))

    adapter = _Adapter(free, purchased)
    stats = asyncio.run(
        SyncService(db=SimpleNamespace(commit=lambda: None))._execute(
            job=SimpleNamespace(id=uuid.uuid4()),
            provider=SimpleNamespace(code=ProviderCode.novofon, id=uuid.uuid4()),
            adapter=adapter,
            connection=ConnectionConfig(base_url="https://example.test", auth_settings={}),
            mode=SyncMode.full,
            stats={"mode": "full", "limitations": [], "categories": {}},
            phase_hook=_hook,
        )
    )
    return stats, adapter.calls, events, persisted


def test_confirmed_empty_free_still_loads_purchased(monkeypatch):
    free = SyncResult(
        fetched=0,
        parsed=0,
        items=[],
        extra_stats={"integrity": {"total_items": 0, "total_items_mismatch": False}},
    )
    purchased = SyncResult(fetched=1, parsed=1, items=[_number("79001234567")])
    stats, calls, events, persisted = _run(
        monkeypatch, free=free, purchased=purchased, previous=[0, 0]
    )
    assert calls == ["free", "purchased"]
    assert ("free", "end", "API вернул 0 свободных номеров") in events
    assert any(phase == "purchased" and event == "end" for phase, event, _detail in events)
    assert "_fatal_error" not in stats
    assert persisted == ["purchased"]
    assert stats.get("_free_cutover_committed") is not True


def test_refused_free_wipe_still_loads_purchased(monkeypatch):
    free = SyncResult(
        fetched=0,
        parsed=0,
        items=[],
        extra_stats={"integrity": {"total_items": 0, "total_items_mismatch": False}},
    )
    purchased = SyncResult(fetched=1, parsed=1, items=[_number("79001234567")])
    stats, calls, events, persisted = _run(
        monkeypatch, free=free, purchased=purchased, previous=[5, 0]
    )
    assert calls == ["free", "purchased"]
    assert any(phase == "free" and event == "fail" for phase, event, _detail in events)
    assert persisted == ["purchased"]
    assert "Refusing wipe" in stats["_fatal_error"]
