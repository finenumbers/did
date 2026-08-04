"""Unit tests for UIS Data API client/parser (no live HTTP)."""

from __future__ import annotations

import asyncio

import pytest

from app.models.enums import InventoryKind
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderParseError
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

    items, envs = asyncio.run(_run())
    assert len(items) == 3
    assert len(envs) == 2


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
