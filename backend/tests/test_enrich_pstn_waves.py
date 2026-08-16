"""PSTN enrich: cache hits, overwrite on miss, no retry storm on failures."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import MagicMock

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.finenumbers.enrich import enrich_catalog_operators


def _raw(
    *,
    status: int = 200,
    body: dict[str, Any] | None = None,
) -> RawHttpResult:
    return RawHttpResult(
        status_code=status,
        body_text="",
        body_json=body,
        headers={},
        elapsed_ms=1.0,
        request_url="https://example.test/lookup",
    )


def _conn() -> ConnectionConfig:
    return ConnectionConfig(base_url="https://example.test", auth_settings={"key": "k"})


def _mock_db(rows: list[tuple]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    db.scalar.return_value = 0
    return db


def test_cache_hit_does_not_call_lookup(monkeypatch):
    calls: list[str] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        calls.append(phone)
        return _raw(body={"found": True, "data": {}})

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "900",
                "rangeStart": 1111111,
                "rangeEnd": 1111111,
                "operator": "CachedOp",
            }
        ],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.client.FinenumbersClient.lookup_phone",
        fake_lookup,
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([(cat_id, "79001111111", None, "900", 1111111)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert calls == []
    assert stats["lookups"] == 0
    assert stats["cache_hits"] >= 1
    assert stats["skipped_already_have_operator"] == 0


def test_filled_operator_still_looks_up_on_cache_miss(monkeypatch):
    calls: list[str] = []
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        calls.append(phone)
        return _raw(
            body={
                "found": True,
                "data": {
                    "abc": "900",
                    "rangeStart": 2222222,
                    "rangeEnd": 2222222,
                    "operator": "FromApi",
                },
            }
        )

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.client.FinenumbersClient.lookup_phone",
        fake_lookup,
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: written.extend(pairs) or len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([(cat_id, "79002222222", "MegaFon", "900", 2222222)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert calls == ["9002222222"]
    assert stats["lookups"] == 1
    assert stats["skipped_already_have_operator"] == 0
    assert written == [(cat_id, "FromApi")]


def test_failed_lookup_not_retried_in_next_wave(monkeypatch):
    calls: list[str] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        calls.append(phone)
        return _raw(status=500, body={"error": "boom"})

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.client.FinenumbersClient.lookup_phone",
        fake_lookup,
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([(cat_id, "79003333333", None, "900", 3333333)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
            max_rounds=8,
        )
    )
    assert calls == ["9003333333"]
    assert stats["lookups"] == 1
    assert stats["errors"] == 1
    assert stats["waves"] == 1


def test_exception_lookup_not_retried(monkeypatch):
    calls: list[str] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        calls.append(phone)
        raise RuntimeError("transport down")

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.client.FinenumbersClient.lookup_phone",
        fake_lookup,
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([(cat_id, "79004444444", None, "900", 4444444)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
            max_rounds=5,
        )
    )
    assert calls == ["9004444444"]
    # Exception path marks phone attempted without incrementing successful HTTP counter
    assert stats["lookups"] == 0
    assert stats["errors"] == 1
    assert stats["waves"] == 1
    assert len(calls) == 1
