"""Exolve provider unit tests (no live API)."""

from __future__ import annotations

import asyncio

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError
from app.providers.exolve import contract, mapper, parser
from app.providers.exolve.client import ExolveClient
from app.providers.exolve.provider import ExolveProvider, _build_free_slices


def _conn() -> ConnectionConfig:
    return ConnectionConfig(
        base_url="https://api.exolve.ru",
        auth_settings={"api_key": "test-key"},
    )


def _raw(body: dict | None = None, text: str = "{}") -> RawHttpResult:
    return RawHttpResult(
        status_code=200,
        body_text=text,
        body_json=body if body is not None else {},
        headers={},
        elapsed_ms=1,
        request_url="https://api.exolve.ru/number/v1/GetFree",
    )


def test_parse_reference_keeps_all_regions_and_leaf_cities():
    data = {
        "regions": [
            {
                "region_id": 10084,
                "parent_region_id": 10084,
                "region_name": "Russia",
                "description": "Россия",
                "region_code": "RU",
            },
            {
                "region_id": 10230,
                "parent_region_id": 10084,
                "region_name": "Moscow",
                "description": "Москва",
                "region_code": "MSK",
            },
            {
                "region_id": 10257,
                "parent_region_id": 10084,
                "region_name": "Salekhard",
                "description": "Салехард",
                "region_code": "SLH",
            },
        ],
        "categories": [
            {
                "category_id": 10000,
                "type_id": 1104,
                "type_name": "DEF",
                "category_name": "REGULAR",
            }
        ],
        "types": [{"type_id": 1104, "type_name": "DEF"}],
    }
    regions, cities, categories = parser.parse_reference(data)
    assert len(regions) == 3
    assert {r.region_external_id for r in regions} == {"10084", "10230", "10257"}
    assert len(cities) == 2
    assert {c.city_external_id for c in cities} == {"10230", "10257"}
    assert cities[0].region_external_id == "10084"
    assert len(categories) == 1


def test_extract_free_numbers_shapes():
    direct = {"numbers": [{"number_code": "79001111111"}]}
    assert len(parser.extract_free_numbers(direct)) == 1
    wrapped = {"result": {"numbers": [{"number_code": "79002222222"}]}}
    assert parser.extract_free_numbers(wrapped)[0]["number_code"] == "79002222222"
    data_wrap = {"data": {"Numbers": [{"number_code": "79003333333"}]}}
    assert len(parser.extract_free_numbers(data_wrap)) == 1
    assert parser.extract_free_numbers({}) == []
    assert parser.extract_free_numbers(None) == []


def test_free_body_supports_category_id():
    client = ExolveClient(_conn())
    body = client._free_body(
        type_id=1104,
        region_id=10230,
        offset=0,
        limit=1,
        random_mode="true",
        category_id=10000,
    )
    assert body["category_id"] == 10000
    assert body["random"] is True
    body_omit = client._free_body(
        type_id=1104, region_id=10230, offset=0, limit=1, random_mode="omit"
    )
    assert "random" not in body_omit
    assert "category_id" not in body_omit


def test_choose_sync_mode_from_probes():
    client = ExolveClient(_conn())
    assert (
        client.choose_sync_mode_from_probes(
            [
                {"probe": "doc_moscow_def_regular", "numbers_len": 1},
                {"probe": "doc_moscow_abc_regular", "numbers_len": 0},
                {"probe": "moscow_def_omit_random", "numbers_len": 0},
                {"probe": "moscow_def_random_false", "numbers_len": 0},
                {"probe": "type_only_def", "numbers_len": 0},
            ]
        )
        == contract.SYNC_MODE_TYPE_REGION_CATEGORY
    )
    assert (
        client.choose_sync_mode_from_probes(
            [
                {"probe": "doc_moscow_def_regular", "numbers_len": 0},
                {"probe": "doc_moscow_abc_regular", "numbers_len": 0},
                {"probe": "moscow_def_omit_random", "numbers_len": 0},
            ]
        )
        == contract.SYNC_MODE_TYPE_REGION
    )
    assert (
        client.choose_sync_mode_from_probes(
            [
                {"probe": "doc_moscow_def_regular", "numbers_len": 1},
                {"probe": "moscow_def_omit_random", "numbers_len": 2},
            ]
        )
        == contract.SYNC_MODE_TYPE_REGION
    )


def test_probe_number_totals():
    totals = ExolveClient.probe_number_totals(
        [
            {"probe": "doc_moscow_def_regular", "numbers_len": 3},
            {"probe": "doc_moscow_abc_regular", "numbers_len": 1},
            {"probe": "moscow_def_omit_random", "numbers_len": 0},
            {"probe": "type_only_def", "numbers_len": 0},
        ]
    )
    assert totals["doc_example_numbers"] == 3
    assert totals["no_category_numbers"] == 0
    assert totals["best_numbers"] == 3


def test_build_free_slices_category_mode_uses_getlist_categories():
    slices = _build_free_slices(
        region_ids=[10084, 10230],
        sync_mode=contract.SYNC_MODE_TYPE_REGION_CATEGORY,
        categories_raw=[
            {"type_id": 1104, "category_id": 10000, "type_name": "DEF"},
            {"type_id": 1104, "category_id": 10010, "type_name": "DEF"},
            {"type_id": 1105, "category_id": 10001, "type_name": "ABC"},
            {"type_id": 1106, "category_id": 10002, "type_name": "KDU"},
        ],
    )
    # DEF: 2 regions × 2 cats; ABC: 2 × 1; KDU: 1 × 1
    assert len(slices) == 2 * 2 + 2 * 1 + 1
    assert (contract.TYPE_DEF, 10230, 10000, "DEF") in slices
    assert (contract.TYPE_KDU, contract.RUSSIA_REGION_ID, 10002, "KDU") in slices
    assert (contract.TYPE_KDU, 10230, 10002, "KDU") not in slices


def test_build_free_slices_ignores_non_docs_getlist_types():
    slices = _build_free_slices(
        region_ids=[10084, 10230],
        sync_mode=contract.SYNC_MODE_TYPE_REGION_CATEGORY,
        categories_raw=[
            {"type_id": 1104, "category_id": 10000, "type_name": "DEF"},
            {"type_id": 1107, "category_id": 10003, "type_name": "CEN"},
            {"type_id": 1110, "category_id": 10006, "type_name": "TollFree"},
            {"type_id": 1106, "category_id": 10002, "type_name": "KDU"},
        ],
    )
    type_ids = {t for t, _, _, _ in slices}
    assert type_ids == {1104, 1105, 1106}  # ABC via docs fallback categories
    assert all(t != 1107 and t != 1110 for t, _, _, _ in slices)
    assert (1106, contract.RUSSIA_REGION_ID, 10002, "KDU") in slices
    assert (1106, 10230, 10002, "KDU") not in slices


def test_build_free_slices_empty_categories_falls_back_to_docs_types():
    slices = _build_free_slices(
        region_ids=[10230],
        sync_mode=contract.SYNC_MODE_TYPE_REGION_CATEGORY,
        categories_raw=[],
    )
    type_ids = {t for t, _, _, _ in slices}
    assert type_ids == set(contract.SYNC_TYPE_IDS)
    assert any(t == contract.TYPE_DEF and c == 10000 for t, _, c, _ in slices)


def test_build_free_slices_type_region_omits_category():
    slices = _build_free_slices(
        region_ids=[10230],
        sync_mode=contract.SYNC_MODE_TYPE_REGION,
        categories_raw=[{"type_id": 1104, "category_id": 10000, "type_name": "DEF"}],
    )
    # Docs types DEF+ABC+KDU; no category_id in body
    assert len(slices) == 3
    assert all(cid is None for _, _, cid, _ in slices)
    assert (contract.TYPE_DEF, 10230, None, "DEF") in slices
    assert (contract.TYPE_KDU, contract.RUSSIA_REGION_ID, None, "KDU") in slices


def test_map_number_prices_and_class():
    item = parser.parse_number_item(
        {
            "number_code": "79300655934",
            "type_name": "DEF",
            "region_name": "Moscow",
            "category_name": "REGULAR",
            "subscription_fee": 150,
            "install_fee": 590,
        },
        region_id=10230,
    )
    num = mapper.map_number(
        item,
        city_lookup={"10230": ("Москва", "10084", "Россия")},
    )
    assert num is not None
    assert num.provider_number_key == "79300655934"
    assert num.buy_price is not None and int(num.buy_price) == 590
    assert num.period_price is not None and int(num.period_price) == 150
    assert num.number_type == "DEF"
    assert num.number_class == "REGULAR"
    assert num.city_name == "Москва"
    assert num.region_name == "Россия"
    assert num.status_raw == contract.STATUS_FREE


def test_iter_free_slice_stops_on_short_page():
    client = ExolveClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(
        *, type_id, region_id, offset, limit=None, random_mode=None, category_id=None
    ):
        calls.append(offset)
        raw = _raw()
        if offset == 0:
            return [{"number_code": "79001111111"}, {"number_code": "79002222222"}], raw
        return [{"number_code": "79003333333"}], raw

    client.get_free_page = fake_page  # type: ignore[method-assign]
    items, _envs = asyncio.run(
        client.iter_free_slice(
            type_id=1104, region_id=10230, category_id=10000, type_label="DEF"
        )
    )
    assert len(items) == 3
    assert calls == [0, 2]


def _empty_probes() -> list[dict]:
    return [
        {"probe": "doc_moscow_def_regular", "numbers_len": 0, "http_status": 200},
        {"probe": "doc_moscow_abc_regular", "numbers_len": 0, "http_status": 200},
        {"probe": "moscow_def_random_false", "numbers_len": 0, "http_status": 200},
        {"probe": "moscow_def_omit_random", "numbers_len": 0, "http_status": 200},
        {"probe": "type_only_def", "numbers_len": 0, "http_status": 200},
    ]


def test_sync_free_builds_type_region_slices(monkeypatch):
    provider = ExolveProvider()
    ref = {
        "regions": [
            {
                "region_id": 10084,
                "parent_region_id": 10084,
                "description": "Россия",
                "region_name": "Russia",
            },
            {
                "region_id": 10230,
                "parent_region_id": 10084,
                "description": "Москва",
                "region_name": "Moscow",
            },
        ],
        "categories": [],
        "types": [],
    }
    seen: list[tuple[int, int, int | None]] = []

    class FakeClient(ExolveClient):
        async def get_reference(self):
            return ref, _raw(ref)

        async def probe_get_free(self):
            return [
                {"probe": "doc_moscow_def_regular", "numbers_len": 0},
                {"probe": "doc_moscow_abc_regular", "numbers_len": 0},
                {"probe": "moscow_def_random_false", "numbers_len": 0},
                {"probe": "moscow_def_omit_random", "numbers_len": 1},
                {"probe": "type_only_def", "numbers_len": 1},
            ]

        async def iter_free_slice(
            self,
            *,
            type_id,
            region_id,
            category_id=None,
            on_progress=None,
            type_label="",
            on_first_raw=None,
        ):
            seen.append((type_id, region_id, category_id))
            raw = _raw({"numbers": []})
            if on_first_raw:
                on_first_raw(raw)
            if type_id == contract.TYPE_DEF and region_id == 10230:
                return (
                    [
                        {
                            "number_code": "79300655934",
                            "type_name": "DEF",
                            "category_name": "REGULAR",
                            "region_name": "Moscow",
                            "install_fee": 1,
                            "subscription_fee": 2,
                        }
                    ],
                    [raw],
                )
            return [], [raw]

    monkeypatch.setattr(provider, "_client", lambda connection, **kw: FakeClient(connection, **kw))
    result = asyncio.run(provider.sync_free_numbers(_conn(), city_lookup={}))
    assert (contract.TYPE_DEF, 10084, None) in seen
    assert (contract.TYPE_DEF, 10230, None) in seen
    assert (contract.TYPE_ABC, 10230, None) in seen
    assert (contract.TYPE_KDU, contract.RUSSIA_REGION_ID, None) in seen
    assert result.parsed == 1
    assert result.extra_stats["integrity"]["sync_mode"] == contract.SYNC_MODE_TYPE_REGION
    assert result.extra_stats["integrity"]["slices_planned"] == 5


def test_sync_free_switches_to_category_mode(monkeypatch):
    provider = ExolveProvider()
    ref = {
        "regions": [
            {
                "region_id": 10230,
                "parent_region_id": 10084,
                "description": "Москва",
                "region_name": "Moscow",
            },
            {
                "region_id": 10084,
                "parent_region_id": 10084,
                "description": "Россия",
                "region_name": "Russia",
            },
        ],
        "categories": [
            {"type_id": 1104, "category_id": 10000},
            {"type_id": 1105, "category_id": 10001},
            {"type_id": 1106, "category_id": 10002},
        ],
        "types": [],
    }
    seen: list[tuple[int, int, int | None]] = []

    class FakeClient(ExolveClient):
        async def get_reference(self):
            return ref, _raw(ref)

        async def probe_get_free(self):
            return [
                {"probe": "doc_moscow_def_regular", "numbers_len": 1},
                {"probe": "doc_moscow_abc_regular", "numbers_len": 1},
                {"probe": "moscow_def_random_false", "numbers_len": 0},
                {"probe": "moscow_def_omit_random", "numbers_len": 0},
                {"probe": "type_only_def", "numbers_len": 0},
            ]

        async def iter_free_slice(
            self,
            *,
            type_id,
            region_id,
            category_id=None,
            on_progress=None,
            type_label="",
            on_first_raw=None,
        ):
            seen.append((type_id, region_id, category_id))
            raw = _raw({"numbers": [{"number_code": "79300655934"}]})
            if on_first_raw:
                on_first_raw(raw)
            if (
                type_id == contract.TYPE_DEF
                and region_id == 10230
                and category_id == 10000
            ):
                return (
                    [
                        {
                            "number_code": "79300655934",
                            "type_name": "DEF",
                            "category_name": "REGULAR",
                            "region_name": "Moscow",
                            "install_fee": 1,
                            "subscription_fee": 2,
                        }
                    ],
                    [raw],
                )
            return [], [raw]

    monkeypatch.setattr(provider, "_client", lambda connection, **kw: FakeClient(connection, **kw))
    result = asyncio.run(provider.sync_free_numbers(_conn(), city_lookup={}))
    assert result.extra_stats["integrity"]["sync_mode"] == (
        contract.SYNC_MODE_TYPE_REGION_CATEGORY
    )
    assert (contract.TYPE_DEF, 10230, 10000) in seen
    assert any(cid is not None for _, _, cid in seen)
    assert result.parsed == 1


def test_sync_free_empty_raises_clear_error(monkeypatch):
    provider = ExolveProvider()
    ref = {
        "regions": [
            {
                "region_id": 10230,
                "parent_region_id": 10084,
                "description": "Москва",
                "region_name": "Moscow",
            },
            {
                "region_id": 10084,
                "parent_region_id": 10084,
                "description": "Россия",
                "region_name": "Russia",
            },
        ],
        "categories": [],
        "types": [],
    }

    class FakeClient(ExolveClient):
        async def get_reference(self):
            return ref, _raw(ref)

        async def probe_get_free(self):
            return _empty_probes()

        async def iter_free_slice(
            self,
            *,
            type_id,
            region_id,
            category_id=None,
            on_progress=None,
            type_label="",
            on_first_raw=None,
        ):
            raw = _raw({"numbers": []})
            if on_first_raw:
                on_first_raw(raw)
            return [], [raw]

    monkeypatch.setattr(provider, "_client", lambda connection, **kw: FakeClient(connection, **kw))
    try:
        asyncio.run(provider.sync_free_numbers(_conn(), city_lookup={}))
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert "Exolve GetFree empty" in str(exc)
        assert "docs examples also empty" in str(exc)
        assert "Exolve LK" in str(exc)
        assert exc.code == "EXOLVE_FREE_EMPTY"


def test_test_connection_reports_doc_vs_no_category(monkeypatch):
    provider = ExolveProvider()
    ref = {
        "regions": [{"region_id": 1}],
        "types": [{"type_id": 1104, "type_name": "DEF"}],
        "categories": [
            {
                "category_id": 10003,
                "type_id": 1107,
                "type_name": "CEN",
                "category_name": "REGULAR",
            },
            {
                "category_id": 10000,
                "type_id": 1104,
                "type_name": "DEF",
                "category_name": "REGULAR",
            },
            {
                "category_id": 10010,
                "type_id": 1104,
                "type_name": "DEF",
                "category_name": "BRONZE",
            },
        ],
    }

    class FakeClient(ExolveClient):
        async def get_reference(self):
            return ref, _raw(ref)

        async def probe_get_free(self):
            return [
                {
                    "probe": "doc_moscow_def_regular",
                    "numbers_len": 2,
                    "json_keys": ["numbers"],
                    "http_status": 200,
                },
                {"probe": "doc_moscow_abc_regular", "numbers_len": 0, "http_status": 200},
                {"probe": "moscow_def_random_false", "numbers_len": 0, "http_status": 200},
                {"probe": "moscow_def_omit_random", "numbers_len": 0, "http_status": 200},
                {"probe": "type_only_def", "numbers_len": 0, "http_status": 200},
            ]

    monkeypatch.setattr(provider, "_client", lambda connection, **kw: FakeClient(connection, **kw))
    result = asyncio.run(provider.test_connection(_conn()))
    assert result.ok is True
    assert "doc_example_numbers=2" in result.message
    assert "no_category_numbers=0" in result.message
    assert "type_region_category" in result.message
    assert "by_type=" not in result.message
    assert result.details["recommended_sync_mode"] == contract.SYNC_MODE_TYPE_REGION_CATEGORY
    assert result.details["categories"] == 3
    assert "categories_list" not in result.details
    assert "categories_by_type" not in result.details


def test_default_page_limit_is_500():
    assert contract.DEFAULT_PAGE_LIMIT == 500
    client = ExolveClient(_conn())
    assert client.page_limit == 500


def test_purchased_unsupported():
    result = asyncio.run(ExolveProvider().sync_purchased_numbers(_conn()))
    assert result.limitations
    assert result.limitations[0].capability == "purchased_numbers"
