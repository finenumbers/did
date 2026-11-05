"""Novofon User API order shop. Fixtures only — no live HTTP."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.models.enums import InventoryKind
from app.modules.sync_engine.safety import confirmed_empty_slice
from app.modules.sync_engine.service import _empty_stage_detail, refuse_slice_detail
from app.providers.dto.common import ConnectionConfig, SyncResult
from app.providers.novofon import contract, mapper, parser
from app.providers.novofon import user_api as user_api_module
from app.providers.novofon.provider import NovofonProvider, _combine_free
from app.providers.novofon.user_api import (
    NovofonUserApi,
    OrderShop,
    UserApiError,
    UserApiRefusal,
    load_order_shop,
    parse_shop_number,
    sign_user_api,
)

_COUNTRY_SIG = "NTVhZTUzZGZmODRkMDQ3MjE4OTA3ODNkMmI2OGM0ZWE0Zjc1Y2JhNg=="
_AVAILABLE_SIG = "NDhkYTI0MGFmYTc2MWIyMmVjNjQxZjZkNmM0NjM0ODliNWQxZTNiMw=="


def _conn(**auth: object) -> ConnectionConfig:
    settings = {"access_token": "token", "api_key": "public-key", **auth}
    return ConnectionConfig(base_url="https://dataapi-jsonrpc.novofon.ru/v2.0", auth_settings=settings)


def _client(handler, **auth: object) -> NovofonUserApi:
    return NovofonUserApi(
        _conn(**auth),
        transport=httpx.MockTransport(handler),
        pace_seconds=0,
        sleep=_no_sleep,
    )


async def _no_sleep(_seconds: float) -> None:
    return None


def _ok(body: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def _data_number(phone: str, buy: str):
    parsed = parser.parse_available_item(
        {
            "phone_number": phone,
            "onetime_payment": buy,
            "monthly_charge": "5",
            "location_name": "Пул",
        }
    )
    mapped = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
    assert mapped is not None
    return mapped


def test_signature_matches_php_hex_hmac_not_raw_digest():
    signed = sign_user_api(
        "/v1/direct_numbers/country/",
        {"language": "ru", "country": "RU"},
        "secret",
    )
    assert signed == _COUNTRY_SIG
    empty = sign_user_api("/v1/direct_numbers/available/3753/", {}, "s")
    assert empty == _AVAILABLE_SIG


def test_request_uses_constant_host_and_signed_header():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok({"status": "success", "info": [{"countryCodeIso": "RU", "name": "Россия"}]})

    client = NovofonUserApi(
        _conn(api_secret="super-secret-value"),
        transport=httpx.MockTransport(handler),
        pace_seconds=0,
    )
    rows = asyncio.run(client.countries())
    assert rows[0]["countryCodeIso"] == "RU"
    request = seen[0]
    assert request.url.host == "api.novofon.com"
    assert "dataapi" not in str(request.url)
    assert "user_id" not in str(request.url)
    assert "super-secret-value" not in str(request.url)
    assert "super-secret-value" not in request.headers["authorization"]
    assert request.headers["authorization"].startswith("public-key:")
    expected = sign_user_api(contract.USER_API_COUNTRIES, {"language": "ru"}, "super-secret-value")
    assert request.headers["authorization"] == f"public-key:{expected}"
    assert client.secret_slot == "api_secret"


def test_country_iso_is_forwarded_unchanged():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/countries/"):
            return _ok({"status": "success", "info": [{"countryCodeIso": "ru", "name": "Россия"}]})
        return _ok({"status": "success", "info": []})

    client = _client(handler)
    shop = asyncio.run(load_order_shop(_conn(), client=client))
    assert shop.russia_missing is False
    assert shop.directions == 0
    assert any("country=ru" in url and "country=RU" not in url for url in seen)


def test_missing_numbers_key_is_not_an_empty_shop():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/countries/"):
            return _ok({"status": "success", "info": [{"countryCodeIso": "RU", "name": "Россия"}]})
        if request.url.path.endswith("/country/"):
            return _ok({"status": "success", "info": [{"id": 10, "name": "Москва"}]})
        return _ok({"status": "success"})

    client = _client(handler)
    with pytest.raises(UserApiRefusal, match="available.numbers missing"):
        asyncio.run(load_order_shop(_conn(), client=client))


def test_empty_numbers_array_is_a_successful_direction():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/countries/"):
            return _ok({"status": "success", "info": [{"countryCodeIso": "RU", "name": "Россия"}]})
        if request.url.path.endswith("/country/"):
            return _ok(
                {
                    "status": "success",
                    "info": [{"id": "10", "name": "Москва", "currency": "RUB"}],
                }
            )
        assert str(request.url).endswith("/available/10/")
        assert "?" not in str(request.url)
        return _ok({"status": "success", "numbers": []})

    shop = asyncio.run(load_order_shop(_conn(), client=_client(handler)))
    assert shop.raw_count == 0
    assert shop.directions == 1
    assert shop.mapped == []
    assert shop.min_per_direction == 0


def test_second_direction_failure_does_not_return_partial_shop():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/countries/"):
            return _ok({"status": "success", "info": [{"countryCodeIso": "RU", "name": "Россия"}]})
        if path.endswith("/country/"):
            return _ok(
                {
                    "status": "success",
                    "info": [
                        {"id": "10", "name": "Москва", "currency": "RUB", "connect_fee": 0},
                        {"id": "11", "name": "Тула", "currency": "RUB"},
                    ],
                }
            )
        if path.endswith("/10/"):
            return _ok({"status": "success", "numbers": [{"id": "a", "number": "+74951234567"}]})
        return httpx.Response(500, json={"status": "error", "message": "down"})

    with pytest.raises(UserApiRefusal, match=r"направление 11") as caught:
        asyncio.run(load_order_shop(_conn(), client=_client(handler)))
    assert "Пул Data API" in caught.value.message
    assert "down" in caught.value.message


def test_bad_direction_id_is_refused_before_available_calls():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/countries/"):
            return _ok({"status": "success", "info": [{"countryCodeIso": "RU", "name": "Россия"}]})
        return _ok({"status": "success", "info": [{"id": "bad/id", "name": "Москва"}]})

    with pytest.raises(UserApiRefusal, match="Негодный id"):
        asyncio.run(load_order_shop(_conn(), client=_client(handler)))
    assert not any("available" in path for path in calls)


def test_auth_failure_is_not_retried_and_names_the_secret_slot():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"status": "error", "message": "Not authorized"})

    with pytest.raises(UserApiError, match="hmac_secret=access_token"):
        asyncio.run(_client(handler).countries())
    assert calls == 1


def test_429_retries_once_when_reset_is_inside_the_window():
    calls = 0
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"status": "error", "message": "limit"},
                headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1000030"},
            )
        return _ok({"status": "success", "info": []})

    client = NovofonUserApi(
        _conn(),
        transport=httpx.MockTransport(handler),
        pace_seconds=0,
        sleep=sleep,
        now=lambda: 1_000_000,
    )
    assert asyncio.run(client.countries()) == []
    assert calls == 2
    assert slept == [30]


def test_pace_between_available_calls_without_rate_headers():
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        return _ok({"status": "success", "numbers": []})

    client = NovofonUserApi(
        _conn(),
        transport=httpx.MockTransport(handler),
        pace_seconds=1.2,
        sleep=sleep,
    )
    asyncio.run(client.available_numbers("10"))
    asyncio.run(client.available_numbers("11"))
    assert slept == [1.2]


def test_rub_zero_is_a_price_and_other_currency_is_not():
    zero = parse_shop_number(
        {"id": "a", "number": "+74951234567"},
        {"id": "10", "name": "Москва", "currency": "RUB", "connect_fee": 0, "monthly_fee": 2},
    )
    assert zero.buy_price == Decimal(0)
    assert zero.period_price == Decimal(2)
    assert zero.raw_payload["location_name"] == "Москва"
    usd = parse_shop_number(
        {"id": "b", "number": "+74957654321", "connect_fee": 9},
        {"id": "11", "name": "Тула", "currency": "USD", "connect_fee": 3, "monthly_fee": 4},
    )
    assert usd.buy_price is None
    assert usd.period_price is None
    assert usd.raw_payload["connect_fee"] == 9
    assert usd.raw_payload["currency"] == "USD"


def test_data_api_row_wins_on_duplicate_msisdn():
    data = _data_number("74951234567", "100")
    shop_parsed = parse_shop_number(
        {"id": "a", "number": "+74951234567", "connect_fee": 1},
        {"id": "10", "name": "Москва", "currency": "rub", "monthly_fee": 2},
    )
    shop_row = mapper.map_number(shop_parsed, inventory_kind=InventoryKind.free)
    assert shop_row is not None
    shop = OrderShop(
        directions=1,
        raw_count=1,
        min_per_direction=1,
        max_per_direction=1,
        secret_slot="access_token",
        russia_missing=False,
        mapped=[shop_row],
    )
    result = _combine_free(
        SyncResult(
            fetched=1,
            parsed=1,
            items=[data],
            extra_stats={"integrity": {"total_items": 1}, "principal": {"summary": "Клиент"}},
        ),
        shop,
    )
    assert len(result.items) == 1
    assert result.items[0].buy_price == Decimal(100)
    assert result.extra_stats["shop"]["hmac_secret"] == "access_token"


def test_missing_key_refuses_even_when_data_api_has_rows(monkeypatch: pytest.MonkeyPatch):
    number = _data_number("74951234567", "100")

    async def _sync(self, connection, **kwargs):
        return SyncResult(
            fetched=1,
            parsed=1,
            items=[number],
            extra_stats={
                "integrity": {"total_items": 1},
                "principal": {"summary": "Клиент «А»", "app_id": 3},
            },
        )

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    auth = {"access_token": "token", "user_id": "15"}
    connection = ConnectionConfig(
        base_url="https://dataapi-jsonrpc.novofon.ru/v2.0",
        auth_settings=auth,
    )
    result = asyncio.run(NovofonProvider().sync_free_numbers(connection))
    assert result.items == []
    assert result.extra_stats["refusal_detail"] == contract.KEY_MISSING_MESSAGE
    assert result.warnings == [contract.KEY_MISSING_MESSAGE]
    assert auth == {"access_token": "token", "user_id": "15"}
    assert (
        confirmed_empty_slice(
            previous=0,
            incoming=0,
            fetched=result.fetched,
            warnings=result.warnings,
            integrity=result.extra_stats["integrity"],
        )
        is False
    )


def test_shop_refusal_drops_data_api_rows(monkeypatch: pytest.MonkeyPatch):
    number = _data_number("74951234567", "100")

    async def _sync(self, connection, **kwargs):
        return SyncResult(fetched=1, parsed=1, items=[number], extra_stats={"integrity": {"total_items": 1}})

    async def _shop(connection, **kwargs):
        raise UserApiRefusal("Витрина заказа не дочитана, направление 11 (Тула): down")

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    monkeypatch.setattr("app.providers.novofon.provider.load_order_shop", _shop)
    result = asyncio.run(NovofonProvider().sync_free_numbers(_conn()))
    assert result.items == []
    assert "направление 11" in result.extra_stats["refusal_detail"]


def test_purchased_does_not_read_the_shop(monkeypatch: pytest.MonkeyPatch):
    async def _shop(*args, **kwargs):
        raise AssertionError("shop")

    async def _iter(self, method, *, on_progress=None):
        return [], [], {"method": method, "fetched": 0, "total_items": 0, "limits": {}}

    monkeypatch.setattr("app.providers.novofon.provider.load_order_shop", _shop)
    monkeypatch.setattr("app.providers.novofon.client.NovofonClient.iter_all", _iter)
    monkeypatch.setattr(
        "app.providers.novofon.client.NovofonClient.resolve_principal",
        _resolved_principal,
    )
    asyncio.run(NovofonProvider().sync_purchased_numbers(_conn()))


async def _resolved_principal(self):
    from app.providers.novofon.client import NovofonPrincipal

    principal = NovofonPrincipal(kind="client", summary="Клиент", app_id=1, name="А")
    self.adopt_principal(principal)
    return principal


def test_refuse_detail_keeps_generic_text_without_custom_detail():
    generic = refuse_slice_detail(
        SimpleNamespace(extra_stats={"integrity": {"total_items": 0}}, fetched=0),
        reason="Empty free fetch; nothing to load",
        incoming=0,
    )
    assert generic == "Empty free fetch; nothing to load"
    custom = refuse_slice_detail(
        SimpleNamespace(
            extra_stats={"refusal_detail": "  нужен Key  ", "integrity": {"total_items": 4}},
            fetched=4,
        ),
        reason="Empty free fetch; nothing to load",
        incoming=0,
    )
    assert custom == "нужен Key"


def test_empty_stage_detail_appends_suffix_after_principal():
    text = _empty_stage_detail(
        "API вернул 0 свободных номеров",
        SimpleNamespace(
            extra_stats={
                "principal": {"summary": "Клиент «А» app_id=1"},
                "empty_suffix": "витрина: направлений=2, номеров=0",
            }
        ),
    )
    assert text == (
        "API вернул 0 свободных номеров. Клиент «А» app_id=1. "
        "витрина: направлений=2, номеров=0"
    )


def test_user_api_module_has_no_mutating_paths():
    text = Path(user_api_module.__file__).read_text()
    assert "direct_numbers/order" not in text
    assert "direct_numbers/prolong" not in text
    assert "client.post" not in text
    assert "client.put" not in text
    assert "connection.base_url" not in text
