"""Unit tests for UIS Data API client/parser (no live HTTP)."""

from __future__ import annotations

import asyncio

import pytest

from app.models.enums import InventoryKind
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderParseError
from app.providers.uis import contract, mapper, parser
from app.providers.uis.client import UisClient


def _raw(body: dict, status: int = 200) -> RawHttpResult:
    return RawHttpResult(
        status_code=status,
        body_text="",
        body_json=body,
        headers={},
        elapsed_ms=1.0,
        request_url="https://dataapi.uiscom.ru/v2.0",
    )


def test_normalize_phone():
    assert parser.normalize_phone("79001234567") == "79001234567"
    assert parser.normalize_phone("89001234567") == "79001234567"
    assert parser.normalize_phone("9001234567") == "79001234567"
    assert parser.normalize_phone("+7 (900) 123-45-67") == "79001234567"
    assert parser.normalize_phone(None) is None
    assert parser.normalize_phone("12345") is None


def test_parse_list_page_ok():
    items, total = parser.parse_list_page(
        _raw(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "data": [{"phone_number": "79001234567"}],
                    "metadata": {"total_items": 42},
                },
            }
        )
    )
    assert len(items) == 1
    assert total == 42


def test_parse_list_page_rpc_error_auth():
    with pytest.raises(ProviderAuthError):
        parser.parse_list_page(
            _raw(
                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "error": {
                        "code": -32001,
                        "message": "Access token has been expired",
                        "data": {"mnemonic": "access_token_expired"},
                    },
                }
            )
        )


def test_map_available():
    parsed = parser.parse_available_item(
        {
            "phone_number": "89001234567",
            "category": "gold",
            "location_name": "Москва",
            "location_mnemonic": "moscow",
            "onetime_payment": 100,
            "monthly_charge": 500,
        }
    )
    mapped = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
    assert mapped is not None
    assert mapped.provider_number_key == "79001234567"
    assert mapped.msisdn == "79001234567"
    assert mapped.abc_code == "900"
    assert mapped.buy_price is not None
    assert mapped.period_price is not None
    assert mapped.number_type == "gold"
    assert mapped.region_name == "Москва"


def test_map_purchased_fallback_key():
    parsed = parser.parse_virtual_item({"id": 99, "status": "active", "category": "usual"})
    mapped = mapper.map_number(parsed, inventory_kind=InventoryKind.purchased)
    assert mapped is not None
    assert mapped.provider_number_key == "uis:99"
    assert mapped.status_raw == "active"


def test_iter_all_pagination(monkeypatch):
    cfg = ConnectionConfig(
        base_url=contract.EXAMPLE_BASE_URL,
        auth_settings={"access_token": "t"},
    )
    client = UisClient(cfg, page_limit=2)
    pages = [
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "data": [{"phone_number": "79000000001"}, {"phone_number": "79000000002"}],
                "metadata": {"total_items": 3},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": "2",
            "result": {
                "data": [{"phone_number": "79000000003"}],
                "metadata": {"total_items": 3},
            },
        },
    ]
    call_n = {"i": 0}

    async def fake_get_page(method, *, offset=0, limit=None):
        body = pages[call_n["i"]]
        call_n["i"] += 1
        return _raw(body)

    monkeypatch.setattr(client, "get_page", fake_get_page)

    async def _run():
        return await client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS)

    items, envs, integrity = asyncio.run(_run())
    assert len(items) == 3
    assert len(envs) == 2
    assert integrity["stop_reason"] == "reached_total"
    assert integrity["total_items_mismatch"] is False


def test_iter_all_continues_after_short_page_when_total_not_reached(monkeypatch):
    """Reproduce 28390/28391: short page must not stop before total."""
    cfg = ConnectionConfig(
        base_url=contract.EXAMPLE_BASE_URL,
        auth_settings={"access_token": "t"},
    )
    client = UisClient(cfg, page_limit=1000)
    total = 28391
    calls: list[int] = []

    async def fake_get_page(method, *, offset=0, limit=None):
        calls.append(offset)
        lim = limit or 1000
        if offset < 28000:
            data = [{"phone_number": f"79{offset + i:09d}"} for i in range(lim)]
        elif offset == 28000:
            data = [{"phone_number": f"79{offset + i:09d}"} for i in range(390)]
        elif offset == 28390:
            data = [{"phone_number": "79999999999"}]
        else:
            data = []
        return _raw(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"data": data, "metadata": {"total_items": total}},
            }
        )

    monkeypatch.setattr(client, "get_page", fake_get_page)
    items, _envs, integrity = asyncio.run(
        client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS)
    )
    assert 28390 in calls
    assert len(items) == total
    assert integrity["stop_reason"] == "reached_total"
    assert integrity["total_items_mismatch"] is False


def test_iter_all_empty_after_shortfall_fails_closed(monkeypatch):
    """total_items shortfall with empty next page → UIS_TOTAL_ITEMS_MISMATCH."""
    cfg = ConnectionConfig(
        base_url=contract.EXAMPLE_BASE_URL,
        auth_settings={"access_token": "t"},
    )
    client = UisClient(cfg, page_limit=1000)
    total = 28391

    async def fake_get_page(method, *, offset=0, limit=None):
        lim = limit or 1000
        if offset < 28000:
            data = [{"phone_number": f"79{offset + i:09d}"} for i in range(lim)]
        elif offset == 28000:
            data = [{"phone_number": f"79{offset + i:09d}"} for i in range(390)]
        else:
            data = []
        return _raw(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"data": data, "metadata": {"total_items": total}},
            }
        )

    monkeypatch.setattr(client, "get_page", fake_get_page)
    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS))
    assert exc_info.value.code == "UIS_TOTAL_ITEMS_MISMATCH"


def test_iter_all_fails_when_truncated_by_max_offset(monkeypatch):
    cfg = ConnectionConfig(
        base_url=contract.EXAMPLE_BASE_URL,
        auth_settings={"access_token": "t"},
    )
    client = UisClient(cfg, page_limit=contract.MAX_LIMIT)
    # Pretend API has more rows than MAX_OFFSET window allows
    total = contract.MAX_OFFSET + 50_000

    async def fake_get_page(method, *, offset=0, limit=None):
        lim = limit or contract.MAX_LIMIT
        if offset > contract.MAX_OFFSET:
            data = []
        else:
            # Compact fake rows (count only matters)
            data = [{"phone_number": "79001234567"}] * lim
        return _raw(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"data": data, "metadata": {"total_items": total}},
            }
        )

    monkeypatch.setattr(client, "get_page", fake_get_page)

    async def _run():
        return await client.iter_all(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS)

    with pytest.raises(ProviderError, match="truncated"):
        asyncio.run(_run())


def test_client_blank_base_url_falls_back():
    cfg = ConnectionConfig(base_url="   ", auth_settings={"access_token": "t"})
    client = UisClient(cfg)
    assert client.base_url == contract.EXAMPLE_BASE_URL.rstrip("/")


def test_client_requires_access_token():
    cfg = ConnectionConfig(base_url=contract.EXAMPLE_BASE_URL, auth_settings={})
    client = UisClient(cfg)
    with pytest.raises(ProviderAuthError, match="access_token"):
        client.require_access_token()


def test_parse_error_non_list():
    with pytest.raises(ProviderParseError):
        parser.parse_list_page(
            _raw({"jsonrpc": "2.0", "id": "1", "result": {"data": {"x": 1}}})
        )
