"""Exolve provider unit tests (no live API)."""

from __future__ import annotations

import asyncio

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError
from app.providers.exolve import contract, mapper, parser
from app.providers.exolve.client import ExolveClient
from app.providers.exolve.provider import ExolveProvider


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


def test_summarize_free_payload():
    summary = parser.summarize_free_payload(
        200,
        {"numbers": [{"number_code": "79300655934"}]},
        '{"numbers":[{"number_code":"79300655934"}]}',
    )
    assert summary["numbers_len"] == 1
    assert summary["sample_number_code"] == "79300655934"
    assert "numbers" in summary["json_keys"]


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


def test_free_body_omits_random_by_default():
    client = ExolveClient(_conn())
    body = client._free_body(type_id=1104, region_id=10230, offset=0, limit=1)
    assert "random" not in body
    body_false = client._free_body(
        type_id=1104, region_id=10230, offset=0, limit=1, random_mode="false"
    )
    assert body_false["random"] is False
    body_type_only = client._free_body(
        type_id=1104, region_id=None, offset=0, limit=1, random_mode="omit"
    )
    assert "region_id" not in body_type_only


def test_choose_random_mode_from_probes():
    client = ExolveClient(_conn())
    assert (
        client.choose_random_mode_from_probes(
            [
                {"probe": "moscow_def_random_false", "numbers_len": 0},
                {"probe": "moscow_def_omit_random", "numbers_len": 1},
            ]
        )
        == "omit"
    )
    assert (
        client.choose_random_mode_from_probes(
            [
                {"probe": "moscow_def_random_false", "numbers_len": 2},
                {"probe": "moscow_def_omit_random", "numbers_len": 0},
            ]
        )
        == "false"
    )


def test_iter_free_slice_stops_on_short_page():
    client = ExolveClient(_conn(), page_limit=2)
    calls: list[int] = []

    async def fake_page(*, type_id, region_id, offset, limit=None, random_mode=None):
        calls.append(offset)
        raw = _raw()
        if offset == 0:
            return [{"number_code": "79001111111"}, {"number_code": "79002222222"}], raw
        return [{"number_code": "79003333333"}], raw

    client.get_free_page = fake_page  # type: ignore[method-assign]
    items, _envs = asyncio.run(
        client.iter_free_slice(type_id=1104, region_id=10230, type_label="DEF")
    )
    assert len(items) == 3
    assert calls == [0, 2]


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
    seen: list[tuple[int, int]] = []

    class FakeClient(ExolveClient):
        async def get_reference(self):
            return ref, _raw(ref)

        async def probe_get_free(self):
            return [
                {
                    "probe": "moscow_def_random_false",
                    "numbers_len": 0,
                    "http_status": 200,
                },
                {
                    "probe": "moscow_def_omit_random",
                    "numbers_len": 1,
                    "http_status": 200,
                },
                {"probe": "type_only_def", "numbers_len": 1, "http_status": 200},
            ]

        async def iter_free_slice(
            self, *, type_id, region_id, on_progress=None, type_label="", on_first_raw=None
        ):
            seen.append((type_id, region_id))
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
    assert (contract.TYPE_DEF, 10084) in seen
    assert (contract.TYPE_DEF, 10230) in seen
    assert (contract.TYPE_ABC, 10230) in seen
    assert (contract.TYPE_KDU, contract.RUSSIA_REGION_ID) in seen
    assert (contract.TYPE_KDU, 10230) not in seen
    assert result.parsed == 1
    assert result.extra_stats["integrity"]["regions_in_reference"] == 2
    assert result.extra_stats["integrity"]["slices_planned"] == 5  # 2+2+1
    assert result.extra_stats["integrity"]["random_mode"] == "omit"


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
            return [
                {"probe": "moscow_def_random_false", "numbers_len": 0},
                {"probe": "moscow_def_omit_random", "numbers_len": 0},
                {"probe": "type_only_def", "numbers_len": 0},
            ]

        async def iter_free_slice(
            self, *, type_id, region_id, on_progress=None, type_label="", on_first_raw=None
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
        assert "Exolve LK" in str(exc)
        assert exc.code == "EXOLVE_FREE_EMPTY"


def test_test_connection_includes_get_free_probes(monkeypatch):
    provider = ExolveProvider()
    ref = {"regions": [{"region_id": 1}], "types": [], "categories": []}

    class FakeClient(ExolveClient):
        async def get_reference(self):
            return ref, _raw(ref)

        async def probe_get_free(self):
            return [
                {
                    "probe": "moscow_def_random_false",
                    "numbers_len": 0,
                    "json_keys": ["numbers"],
                    "http_status": 200,
                    "body_text_preview": '{"numbers":[]}',
                },
                {
                    "probe": "moscow_def_omit_random",
                    "numbers_len": 0,
                    "json_keys": ["numbers"],
                    "http_status": 200,
                },
                {
                    "probe": "type_only_def",
                    "numbers_len": 0,
                    "json_keys": ["numbers"],
                    "http_status": 200,
                },
            ]

    monkeypatch.setattr(provider, "_client", lambda connection, **kw: FakeClient(connection, **kw))
    result = asyncio.run(provider.test_connection(_conn()))
    assert result.ok is True
    assert "GetFree canary" in result.message
    assert result.details["get_free_best_numbers"] == 0
    assert len(result.details["get_free_probes"]) == 3


def test_purchased_unsupported():
    result = asyncio.run(ExolveProvider().sync_purchased_numbers(_conn()))
    assert result.limitations
    assert result.limitations[0].capability == "purchased_numbers"
