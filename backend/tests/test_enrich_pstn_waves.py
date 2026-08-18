"""PSTN enrich: cache hits, overwrite on miss, sentinel on confirmed absence."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.modules.catalog.geo_policy import GEO_TOLLFREE
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError
from app.providers.finenumbers import contract
from app.providers.finenumbers.enrich import (
    LookupClass,
    classify_lookup_response,
    enrich_catalog_operators,
)


def _raw(
    *,
    status: int = 200,
    body: dict[str, Any] | None = None,
    body_text: str = "",
) -> RawHttpResult:
    return RawHttpResult(
        status_code=status,
        body_text=body_text,
        body_json=body,
        headers={},
        elapsed_ms=1.0,
        request_url="https://example.test/lookup",
    )


def _conn() -> ConnectionConfig:
    return ConnectionConfig(base_url="https://example.test", auth_settings={"key": "k"})


def _cat(
    cat_id,
    msisdn: str,
    operator,
    abc: str,
    local: int,
    city=None,
    region=None,
):
    return (cat_id, msisdn, operator, abc, local, city, region)


def _upd(cat_id, operator: str, apply_geo: bool = False, city=None, region=None):
    return (cat_id, operator, apply_geo, city, region)


def _mock_db(rows: list[tuple]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    db.scalar.return_value = 0
    return db


def test_classify_lookup_absent_and_error():
    assert classify_lookup_response(_raw(body={"found": False})) is LookupClass.absent
    assert classify_lookup_response(_raw(status=404, body={"error": "nf"})) is LookupClass.absent
    assert classify_lookup_response(_raw(status=400, body={"error": "bad"})) is LookupClass.absent
    assert classify_lookup_response(_raw(status=422)) is LookupClass.absent
    assert classify_lookup_response(_raw(status=500, body={"error": "boom"})) is LookupClass.error
    assert classify_lookup_response(_raw(status=401)) is LookupClass.error
    assert (
        classify_lookup_response(
            _raw(
                body={
                    "found": True,
                    "data": {"abc": "900", "rangeStart": 1, "rangeEnd": 1, "operator": "Op"},
                }
            )
        )
        is LookupClass.found
    )


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
                "garTerritory": "г. Москва|г. Москва",
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
    db = _mock_db([_cat(cat_id, "79001111111", None, "900", 1111111)])

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
    db = _mock_db([_cat(cat_id, "79002222222", "MegaFon", "900", 2222222)])

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
    assert written == [_upd(cat_id, "FromApi")]


def test_found_false_writes_not_in_registry_and_passes_coverage(monkeypatch):
    calls: list[str] = []
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        calls.append(phone)
        return _raw(body={"found": False})

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
    db = _mock_db([_cat(cat_id, "79005555555", 'ООО «Фронтир Нетворк»', "900", 5555555)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=True,
            concurrency=2,
        )
    )
    assert calls == ["9005555555"]
    assert written == [
        _upd(
            cat_id,
            contract.OPERATOR_NOT_IN_REGISTRY,
            True,
            contract.OPERATOR_NOT_IN_REGISTRY,
            contract.OPERATOR_NOT_IN_REGISTRY,
        )
    ]
    assert stats["not_in_registry"] == 1
    assert stats["missing"] == 0
    assert stats["errors"] == 0


def test_http_404_writes_not_in_registry_and_passes_coverage(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        return _raw(status=404, body={"error": "not found"}, body_text='{"error":"not found"}')

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
    db = _mock_db([_cat(cat_id, "73432888870", None, "343", 2888870)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=True,
            concurrency=2,
        )
    )
    assert written == [
        _upd(
            cat_id,
            contract.OPERATOR_NOT_IN_REGISTRY,
            True,
            contract.OPERATOR_NOT_IN_REGISTRY,
            contract.OPERATOR_NOT_IN_REGISTRY,
        )
    ]
    assert stats["not_in_registry"] == 1
    assert stats["errors"] == 0
    assert stats["missing"] == 0


def test_http_500_fails_coverage_without_sentinel(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
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
        lambda db, pairs: written.extend(pairs) or len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([_cat(cat_id, "79003333333", "KeepMe", "900", 3333333)])

    with pytest.raises(ProviderError) as exc:
        asyncio.run(
            enrich_catalog_operators(
                db,
                connection=_conn(),
                require_full_coverage=True,
                concurrency=2,
                max_rounds=3,
            )
        )
    assert exc.value.code == "OPERATOR_ENRICHMENT_INCOMPLETE"
    assert "errors=" in str(exc.value)
    assert written == []


def test_failed_lookup_retried_across_waves(monkeypatch):
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
    db = _mock_db([_cat(cat_id, "79003333333", None, "900", 3333333)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
            max_rounds=3,
        )
    )
    assert calls == ["9003333333", "9003333333", "9003333333"]
    assert stats["lookups"] == 3
    assert stats["errors"] == 3
    assert stats["waves"] == 3


def test_exception_lookup_retried_across_waves_preserves_operator(monkeypatch):
    calls: list[str] = []
    written: list[tuple] = []

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
        lambda db, pairs: written.extend(pairs) or len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([_cat(cat_id, "79004444444", "KeepMe", "900", 4444444)])

    stats = asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
            max_rounds=2,
        )
    )
    assert calls == ["9004444444", "9004444444"]
    assert stats["lookups"] == 0
    assert stats["errors"] == 2
    assert stats["waves"] == 2
    assert written == []


def test_cache_hit_writes_gar_geo_even_if_operator_matches(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        raise AssertionError("lookup must not run on cache hit")

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "495",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "г.о. город Екатеринбург|Свердловская область",
            }
        ],
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
    db = _mock_db(
        [_cat(cat_id, "74951000000", "CachedOp", "495", 1000000, "SipOutCity", "SipOutRegion")]
    )
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [_upd(cat_id, "CachedOp", True, "Екатеринбург", "Свердловская область")]


def test_empty_gar_does_not_overwrite_provider_geo(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        return _raw(body={"found": True, "data": {}})

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "495",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "",
            },
            {
                "abc": "812",
                "rangeStart": 1,
                "rangeEnd": 1,
                "operator": "OtherOp",
                "garTerritory": "г. Санкт-Петербург|г. Санкт-Петербург",
            },
        ],
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
    db = _mock_db(
        [_cat(cat_id, "74951000000", "CachedOp", "495", 1000000, "SipOutCity", "SipOutRegion")]
    )
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == []


def test_lookup_applies_gar_territory(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        return _raw(
            body={
                "found": True,
                "data": {
                    "abc": "812",
                    "rangeStart": 1111111,
                    "rangeEnd": 1111111,
                    "operator": "FromApi",
                    "garTerritory": "г. Санкт-Петербург|г. Санкт-Петербург",
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
    db = _mock_db([_cat(cat_id, "78121111111", None, "812", 1111111, "OldCity", "OldRegion")])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [_upd(cat_id, "FromApi", True, "Санкт-Петербург", "Санкт-Петербург")]


def test_enrich_refreshes_cache_when_gar_missing(monkeypatch):
    written: list[tuple] = []
    refresh_calls: list[int] = []
    loads = [
        [
            {
                "abc": "495",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "",
            }
        ],
        [
            {
                "abc": "495",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "г.о. город Екатеринбург|Свердловская область",
            }
        ],
    ]

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        raise AssertionError("lookup must not run on cache hit")

    async def fake_refresh(db):
        refresh_calls.append(1)
        return {}

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: loads.pop(0),
    )
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.refresh_enabled_caches",
        fake_refresh,
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
    db = _mock_db([_cat(cat_id, "74951000000", None, "495", 1000000)])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert refresh_calls == [1]
    assert written == [_upd(cat_id, "CachedOp", True, "Екатеринбург", "Свердловская область")]


def test_enrich_fails_when_gar_still_empty_after_refresh(monkeypatch):
    refresh_calls: list[int] = []

    async def fake_refresh(db):
        refresh_calls.append(1)
        return {}

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "495",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "",
            }
        ],
    )
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.refresh_enabled_caches",
        fake_refresh,
    )

    db = _mock_db([_cat(uuid.uuid4(), "74951000000", None, "495", 1000000)])
    with pytest.raises(ProviderError) as exc:
        asyncio.run(
            enrich_catalog_operators(
                db,
                connection=_conn(),
                require_full_coverage=False,
                concurrency=2,
            )
        )
    assert exc.value.code == "PSTN_GAR_CACHE_EMPTY"
    assert refresh_calls == [1]


def test_found_tollfree_writes_russia_even_with_gar(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        raise AssertionError("lookup must not run on cache hit")

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "800",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "г. Самара|Самарская область",
            }
        ],
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
    db = _mock_db([_cat(cat_id, "78001000000", None, "800", 1000000)])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [_upd(cat_id, "CachedOp", True, GEO_TOLLFREE, GEO_TOLLFREE)]


def test_found_tollfree_empty_gar_still_writes_russia(monkeypatch):
    written: list[tuple] = []

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "800",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "",
            },
            {
                "abc": "812",
                "rangeStart": 1,
                "rangeEnd": 1,
                "operator": "OtherOp",
                "garTerritory": "г. Санкт-Петербург|г. Санкт-Петербург",
            },
        ],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: written.extend(pairs) or len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([_cat(cat_id, "78001000000", "CachedOp", "800", 1000000)])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [_upd(cat_id, "CachedOp", True, GEO_TOLLFREE, GEO_TOLLFREE)]


def test_absent_tollfree_writes_sentinel_not_russia(monkeypatch):
    written: list[tuple] = []

    async def fake_lookup(self, phone: str) -> RawHttpResult:
        return _raw(body={"found": False})

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
    db = _mock_db([_cat(cat_id, "78005555555", None, "800", 5555555)])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [
        _upd(
            cat_id,
            contract.OPERATOR_NOT_IN_REGISTRY,
            True,
            contract.OPERATOR_NOT_IN_REGISTRY,
            contract.OPERATOR_NOT_IN_REGISTRY,
        )
    ]


def test_mobile_collapses_moscow_oblast_pair(monkeypatch):
    written: list[tuple] = []

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "900",
                "rangeStart": 1111111,
                "rangeEnd": 1111111,
                "operator": "CachedOp",
                "garTerritory": "г. Москва|Московская область",
            }
        ],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: written.extend(pairs) or len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([_cat(cat_id, "79001111111", None, "900", 1111111)])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [_upd(cat_id, "CachedOp", True, "Москва", "Москва")]


def test_geographic_keeps_moscow_and_oblast(monkeypatch):
    written: list[tuple] = []

    monkeypatch.setattr(
        "app.providers.finenumbers.enrich.load_enabled_ranges_for_enrich",
        lambda db: [
            {
                "abc": "495",
                "rangeStart": 1000000,
                "rangeEnd": 1000000,
                "operator": "CachedOp",
                "garTerritory": "г. Москва|Московская область",
            }
        ],
    )
    monkeypatch.setattr(
        "app.providers.finenumbers.enrich._bulk_update_operators",
        lambda db, pairs: written.extend(pairs) or len(pairs),
    )

    cat_id = uuid.uuid4()
    db = _mock_db([_cat(cat_id, "74951000000", None, "495", 1000000)])
    asyncio.run(
        enrich_catalog_operators(
            db,
            connection=_conn(),
            require_full_coverage=False,
            concurrency=2,
        )
    )
    assert written == [_upd(cat_id, "CachedOp", True, "Москва", "Московская область")]
