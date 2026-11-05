"""Unit tests for Novofon Data API client/parser (no live HTTP)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.models.enums import InventoryKind, ProviderCode
from app.modules.pstn_inn_cache.service import REQUIRED_INNS, REQUIRED_OPERATORS
from app.modules.sync_engine.unified import PROVIDER_ORDER
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.novofon import contract, mapper, parser
from app.providers.novofon.client import NovofonClient
from app.providers.novofon.provider import NovofonProvider
from app.providers.retry import RetryPolicy


def _raw(body: dict, status: int = 200) -> RawHttpResult:
    return RawHttpResult(
        status_code=status,
        body_text="",
        body_json=body,
        headers={},
        elapsed_ms=1.0,
        request_url=contract.EXAMPLE_BASE_URL,
    )


def _page(total: int, rows: list[dict]) -> RawHttpResult:
    return _raw(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"data": rows, "metadata": {"total_items": total}},
        }
    )


def _client(**auth: object) -> NovofonClient:
    settings = {"access_token": "token", **auth}
    return NovofonClient(
        ConnectionConfig(base_url="https://example.test/v2.0", auth_settings=settings),
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0),
    )


def test_novofon_is_ru_provider_after_uis():
    assert ProviderCode.novofon in PROVIDER_ORDER
    assert PROVIDER_ORDER.index(ProviderCode.novofon) == PROVIDER_ORDER.index(ProviderCode.uis) + 1
    assert NovofonProvider().capabilities()["dictionaries"]["supported"] is False


def test_required_operator_novofon_inn():
    assert "9703126821" in REQUIRED_INNS
    by_inn = {inn: name for name, inn in REQUIRED_OPERATORS}
    assert by_inn["9703126821"] == "ООО «НОВОФОН-ОС»"


def test_parse_available_normalizes_phone_and_prices():
    item = parser.parse_available_item(
        {
            "phone_number": "8 (900) 123-45-67",
            "onetime_payment": "100.50",
            "monthly_charge": "10",
            "location_name": "Москва",
            "location_mnemonic": "msk",
            "category": "gold",
        }
    )
    mapped = mapper.map_number(item, inventory_kind=InventoryKind.free)
    assert mapped is not None
    assert mapped.msisdn == "79001234567"
    assert mapped.provider_number_key == "79001234567"
    assert mapped.buy_price == Decimal("100.50")
    assert mapped.period_price == Decimal(10)
    assert mapped.region_name is None
    assert mapped.city_name is None
    assert mapped.region_external_id is None
    assert mapped.raw_payload["location_name"] == "Москва"


def test_non_russian_phone_is_not_a_catalog_row():
    item = parser.parse_virtual_item(
        {"id": 9, "virtual_phone_number": "+44 20 7946 0958", "status": "active"}
    )
    assert item.provider_number_key is None
    assert mapper.map_number(item, inventory_kind=InventoryKind.purchased) is None


def test_purchased_keeps_status_and_drops_prices():
    item = parser.parse_virtual_item(
        {
            "id": 3,
            "virtual_phone_number": "79001234567",
            "status": "active",
            "category": "platinum",
            "activation_date": "2024-01-02",
            "onetime_payment": "999",
        }
    )
    mapped = mapper.map_number(item, inventory_kind=InventoryKind.purchased)
    assert mapped is not None
    assert mapped.buy_price is None
    assert mapped.period_price is None
    assert mapped.status_raw == "active"
    assert mapped.date_from == "2024-01-02"
    assert mapped.provider_number_key == "79001234567"


def test_total_items_reads_meta_data_alias():
    _items, total = parser.parse_list_page(
        _raw({"result": {"data": [], "meta_data": {"total_items": 4}}})
    )
    assert total == 4


def test_access_token_expired_is_auth_error():
    with pytest.raises(ProviderAuthError):
        parser.parse_list_page(
            _raw(
                {
                    "error": {
                        "code": -32001,
                        "message": "expired",
                        "data": {"mnemonic": "access_token_expired"},
                    }
                }
            )
        )


def test_limit_retry_wait_minute_only():
    minute = _raw(
        {
            "error": {
                "code": -32029,
                "message": "minute limit",
                "data": {
                    "mnemonic": "limit_exceeded",
                    "params": {"limit_type": "minute"},
                    "metadata": {"limits": {"minute_reset": 15}},
                },
            }
        }
    )
    day = _raw(
        {
            "error": {
                "code": -32029,
                "message": "per day",
                "data": {
                    "mnemonic": "limit_exceeded",
                    "params": {"limit_type": "day"},
                    "metadata": {"limits": {"minute_reset": 15}},
                },
            }
        }
    )
    assert parser.limit_retry_wait(minute) == 15
    assert parser.limit_retry_wait(day) is None


def test_blank_base_url_and_bad_user_id():
    client = NovofonClient(
        ConnectionConfig(base_url="  ", auth_settings={}),
        retry=RetryPolicy(max_attempts=1),
    )
    assert client.base_url == contract.EXAMPLE_BASE_URL
    with pytest.raises(ProviderAuthError):
        client.require_access_token()
    with pytest.raises(ProviderAuthError):
        NovofonClient(
            ConnectionConfig(
                base_url="https://example.test",
                auth_settings={"access_token": "t", "user_id": "abc"},
            )
        )


def test_page_limits_differ_by_method():
    client = _client()
    assert client.limit_for(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS) == 10_000
    assert client.limit_for(contract.METHOD_VIRTUAL_NUMBERS) == 1_000


def test_null_category_filter_reaches_json_body(monkeypatch: pytest.MonkeyPatch):
    seen: dict = {}

    class _Response:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = "{}"
            self.headers: dict[str, str] = {}
            self.url = contract.EXAMPLE_BASE_URL

        def json(self):
            return {"result": {"data": [], "metadata": {"total_items": 0}}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            seen["json"] = json
            return _Response()

    monkeypatch.setattr("app.providers.novofon.client.httpx.AsyncClient", _Client)
    client = NovofonClient(
        ConnectionConfig(
            base_url="https://example.test/v2.0",
            auth_settings={"access_token": "token", "user_id": "42"},
        ),
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0),
    )

    async def _run():
        return await client.get_page(
            contract.METHOD_VIRTUAL_NUMBERS,
            offset=0,
            limit=1,
            category_is_null=True,
        )

    asyncio.run(_run())
    params = seen["json"]["params"]
    assert params["user_id"] == 42
    assert params["filter"] == {"field": "category", "operator": "=", "value": None}


def test_minute_limit_retries_once(monkeypatch: pytest.MonkeyPatch):
    slept: list[float] = []

    async def _sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.providers.novofon.client.asyncio.sleep", _sleep)
    bodies = [
        _raw(
            {
                "error": {
                    "code": -32029,
                    "message": "minute limit",
                    "data": {
                        "mnemonic": "limit_exceeded",
                        "params": {"limit_type": "minute"},
                        "metadata": {"limits": {"minute_reset": 12}},
                    },
                }
            }
        ),
        _page(0, []),
    ]

    async def _call(method, params=None):
        return bodies.pop(0)

    client = _client()
    client.call = _call  # type: ignore[method-assign]

    async def _run():
        raw = await client.get_page(contract.METHOD_VIRTUAL_NUMBERS, limit=1)
        parser.parse_list_page(raw)

    asyncio.run(_run())
    assert slept == [12]
    assert bodies == []


def test_short_page_continues_until_total():
    client = _client()
    client._page_limit_override = 2
    pages = {
        0: _page(5, [{"phone_number": "79000000001"}, {"phone_number": "79000000002"}]),
        2: _page(5, [{"phone_number": "79000000003"}, {"phone_number": "79000000004"}]),
        4: _page(5, [{"phone_number": "79000000005"}]),
    }

    async def _get_page(method, *, offset=0, limit=None, category=None, category_is_null=False):
        return pages[offset]

    client.get_page = _get_page  # type: ignore[method-assign]

    async def _run():
        return await client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS)

    items, _envelopes, integrity = asyncio.run(_run())
    assert [row["phone_number"] for row in items] == [
        "79000000001",
        "79000000002",
        "79000000003",
        "79000000004",
        "79000000005",
    ]
    assert integrity["total_items_mismatch"] is False


def test_empty_page_inside_window_warns_and_keeps_rows():
    client = _client()
    client._page_limit_override = 2

    async def _get_page(method, *, offset=0, limit=None, category=None, category_is_null=False):
        if offset == 0:
            return _page(5, [{"phone_number": "79000000001"}, {"phone_number": "79000000002"}])
        return _page(5, [])

    client.get_page = _get_page  # type: ignore[method-assign]
    items, _envelopes, integrity = asyncio.run(
        client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS)
    )
    assert len(items) == 2
    assert integrity["total_items_mismatch"] is True
    assert integrity["stop_reason"] == "empty_page"


def test_category_partition_matches_unfiltered_total():
    client = _client()
    client._page_limit_override = 10
    window = contract.MAX_OFFSET + 10
    expected = window + 1
    usual_rows = [{"phone_number": "79000000001"}] * window

    async def _get_page(method, *, offset=0, limit=None, category=None, category_is_null=False):
        if category is None and not category_is_null:
            return _page(expected, [{"phone_number": "79000000001"}])
        if category == "usual":
            return _page(window, usual_rows)
        if category == "bronze":
            return _page(1, [{"phone_number": "79000000002"}])
        return _page(0, [])

    client.get_page = _get_page  # type: ignore[method-assign]
    items, _envelopes, integrity = asyncio.run(
        client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS)
    )
    assert len(items) == expected
    assert integrity["partitioned"] is True
    assert integrity["stop_reason"] == "category_partition"


def test_category_partition_count_mismatch_raises():
    client = _client()
    client._page_limit_override = 10
    expected = contract.MAX_OFFSET + 10 + 1

    async def _get_page(method, *, offset=0, limit=None, category=None, category_is_null=False):
        if category is None and not category_is_null:
            return _page(expected, [{"phone_number": "79000000001"}])
        if category == "usual":
            return _page(1, [{"phone_number": "79000000001"}])
        return _page(0, [])

    client.get_page = _get_page  # type: ignore[method-assign]
    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS))
    assert exc.value.code == "NOVOFON_PAGINATION_TRUNCATED"


def test_category_slice_over_window_raises():
    client = _client()
    client._page_limit_override = 10
    window = contract.MAX_OFFSET + 10
    expected = window + 1

    async def _get_page(method, *, offset=0, limit=None, category=None, category_is_null=False):
        if category is None and not category_is_null:
            return _page(expected, [{"phone_number": "79000000001"}])
        if category == "usual":
            return _page(window + 1, [{"phone_number": "79000000001"}])
        return _page(0, [])

    client.get_page = _get_page  # type: ignore[method-assign]
    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS))
    assert exc.value.code == "NOVOFON_PAGINATION_TRUNCATED"
