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
from app.modules.sync_engine.service import (
    _empty_stage_detail,
    _with_stage_note,
    refuse_slice_detail,
)
from app.providers.dto.common import ConnectionConfig, SyncResult
from app.providers.novofon import contract, mapper, parser
from app.providers.novofon import user_api as user_api_module
from app.providers.novofon.provider import NovofonProvider
from app.providers.novofon.user_api import (
    NovofonUserApi,
    UserApiError,
    UserApiRefusal,
    load_order_shop,
    load_owned_numbers,
    parse_owned_number,
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
    assert shop.countries == 1
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


def test_stage_note_is_appended_without_becoming_a_warning():
    result = SyncResult(extra_stats={"stage_note": contract.KEY_MISSING_MESSAGE})
    assert _with_stage_note("fetched=1", result) == f"fetched=1. {contract.KEY_MISSING_MESSAGE}"
    assert _with_stage_note("fetched=1", SyncResult()) == "fetched=1"


def test_missing_key_keeps_data_api_rows(monkeypatch: pytest.MonkeyPatch):
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
    assert result.items == [number]
    assert result.warnings == []
    assert "shop" not in result.extra_stats
    assert "refusal_detail" not in result.extra_stats
    assert auth == {"access_token": "token", "user_id": "15"}


def test_missing_key_and_empty_pool_is_confirmed_empty(monkeypatch: pytest.MonkeyPatch):
    async def _sync(self, connection, **kwargs):
        return SyncResult(
            fetched=0,
            parsed=0,
            items=[],
            extra_stats={"integrity": {"total_items": 0}, "principal": {"summary": "Клиент"}},
        )

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    result = asyncio.run(
        NovofonProvider().sync_free_numbers(
            ConnectionConfig(
                base_url="https://dataapi-jsonrpc.novofon.ru/v2.0",
                auth_settings={"access_token": "token"},
            )
        )
    )
    assert result.items == []
    assert result.warnings == []
    assert result.extra_stats["empty_suffix"] == (
        f"{contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS} total_items=0"
    )
    assert confirmed_empty_slice(
        previous=0,
        incoming=0,
        fetched=result.fetched,
        warnings=result.warnings,
        integrity=result.extra_stats["integrity"],
    )


def test_free_keeps_data_api_rows_when_api_key_is_set(monkeypatch: pytest.MonkeyPatch):
    number = _data_number("74951234567", "100")

    async def _sync(self, connection, **kwargs):
        return SyncResult(
            fetched=1,
            parsed=1,
            items=[number],
            extra_stats={"integrity": {"fetched": 1, "total_items": 1}},
        )

    async def _shop(*args, **kwargs):
        raise AssertionError("shop")

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    monkeypatch.setattr("app.providers.novofon.user_api.load_order_shop", _shop)
    result = asyncio.run(NovofonProvider().sync_free_numbers(_conn()))
    assert result.items == [number]
    assert result.warnings == []
    assert "refusal_detail" not in result.extra_stats


def test_free_short_page_refuses_the_slice(monkeypatch: pytest.MonkeyPatch):
    number = _data_number("74951234567", "100")

    async def _sync(self, connection, **kwargs):
        return SyncResult(
            fetched=1,
            parsed=1,
            items=[number],
            extra_stats={"integrity": {"fetched": 1, "total_items": 4, "total_items_mismatch": True}},
        )

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    result = asyncio.run(NovofonProvider().sync_free_numbers(_conn()))
    assert result.items == []
    assert result.warnings
    assert "total_items=4" in result.extra_stats["refusal_detail"]
    assert confirmed_empty_slice(
        previous=0,
        incoming=0,
        fetched=result.fetched,
        warnings=result.warnings,
        integrity=result.extra_stats["integrity"],
    ) is False


def test_free_unmapped_number_refuses_the_slice(monkeypatch: pytest.MonkeyPatch):
    async def _sync(self, connection, **kwargs):
        return SyncResult(
            fetched=1,
            parsed=0,
            items=[],
            unmapped_raw=[{"phone_number": "123"}],
            extra_stats={"integrity": {"fetched": 1, "total_items": 1}},
        )

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    result = asyncio.run(NovofonProvider().sync_free_numbers(_conn()))
    assert result.items == []
    assert "не разобрано номеров=1" in result.extra_stats["refusal_detail"]


def test_purchased_does_not_read_the_shop(monkeypatch: pytest.MonkeyPatch):
    async def _shop(*args, **kwargs):
        raise AssertionError("shop")

    async def _owned(*args, **kwargs):
        from app.providers.novofon.user_api import OwnedNumbers

        return OwnedNumbers(raw_count=0, secret_slot="access_token")

    async def _iter(self, method, *, on_progress=None):
        return [], [], {"method": method, "fetched": 0, "total_items": 0, "limits": {}}

    monkeypatch.setattr("app.providers.novofon.user_api.load_order_shop", _shop)
    monkeypatch.setattr("app.providers.novofon.provider.load_owned_numbers", _owned)
    monkeypatch.setattr("app.providers.novofon.client.NovofonClient.iter_all", _iter)
    monkeypatch.setattr(
        "app.providers.novofon.client.NovofonClient.resolve_principal",
        _resolved_principal,
    )
    result = asyncio.run(NovofonProvider().sync_purchased_numbers(_conn()))
    assert result.warnings == []
    assert result.extra_stats["owned"]["numbers"] == 0


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


def test_every_country_is_walked_and_direction_id_and_mask_are_absent():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        path = request.url.path
        if path.endswith("/countries/"):
            return _ok(
                {
                    "status": "success",
                    "info": [
                        {"countryCodeIso": "DE", "name": "Germany"},
                        {"countryCodeIso": "ru", "name": "Россия"},
                    ],
                }
            )
        if path.endswith("/country/"):
            assert "direction_id" not in str(request.url)
            iso = request.url.params["country"]
            direction_id = "20" if iso == "DE" else "10"
            return _ok({"status": "success", "info": [{"id": direction_id, "name": iso, "currency": "RUB"}]})
        assert "mask" not in str(request.url)
        assert "?" not in str(request.url)
        if path.endswith("/20/"):
            return _ok({"status": "success", "numbers": [{"id": "g", "number": "+4930123456"}]})
        return _ok({"status": "success", "numbers": [{"id": "r", "number": "+74951234567"}]})

    shop = asyncio.run(load_order_shop(_conn(), client=_client(handler)))
    assert shop.countries == 2
    assert shop.directions == 2
    assert shop.raw_count == 2
    keys = {item.provider_number_key for item in shop.mapped}
    assert keys == {"DE:4930123456", "74951234567"}
    foreign = next(item for item in shop.mapped if item.provider_number_key.startswith("DE:"))
    assert foreign.msisdn == "4930123456"
    assert foreign.number_local == "4930123456"
    assert foreign.abc_code is None
    assert foreign.city_name == "DE"
    assert foreign.region_name == "Germany"
    assert any("country=DE" in url for url in seen)
    assert any("country=ru" in url for url in seen)


def test_foreign_ten_digits_are_not_prefixed_and_plus_seven_msisdn_stays_empty():
    short = parse_shop_number(
        {"id": "a", "number": "3012345678"},
        {"id": "1", "name": "Berlin", "currency": "EUR", "monthly_fee": 4},
        country_iso="DE",
        country_name="Germany",
    )
    mapped_short = mapper.map_number(short, inventory_kind=InventoryKind.free)
    assert mapped_short is not None
    assert mapped_short.provider_number_key == "DE:3012345678"
    assert mapped_short.msisdn == "3012345678"
    assert mapped_short.buy_price is None
    kz = parse_shop_number(
        {"id": "b", "number": "+77001234567"},
        {"id": "2", "name": "Almaty", "currency": "RUB", "connect_fee": 0, "monthly_fee": 3},
        country_iso="KZ",
        country_name="Kazakhstan",
    )
    mapped_kz = mapper.map_number(kz, inventory_kind=InventoryKind.free)
    assert mapped_kz is not None
    assert mapped_kz.provider_number_key == "KZ:77001234567"
    assert mapped_kz.msisdn is None
    assert mapped_kz.number_local == "77001234567"
    assert mapped_kz.buy_price == Decimal(0)
    assert mapped_kz.period_price == Decimal(3)
    assert mapped_kz.city_name == "Almaty"
    assert mapped_kz.region_name == "Kazakhstan"


def test_duplicate_shop_key_refuses_the_whole_slice():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/countries/"):
            return _ok({"status": "success", "info": [{"countryCodeIso": "DE", "name": "Germany"}]})
        if path.endswith("/country/"):
            return _ok(
                {
                    "status": "success",
                    "info": [
                        {"id": "1", "name": "Berlin"},
                        {"id": "2", "name": "Hamburg"},
                    ],
                }
            )
        return _ok({"status": "success", "numbers": [{"id": "a", "number": "+4930123456"}]})

    with pytest.raises(UserApiRefusal, match="повтор ключа"):
        asyncio.run(load_order_shop(_conn(), client=_client(handler)))


def test_second_country_501_does_not_return_the_first_country():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/countries/"):
            return _ok(
                {
                    "status": "success",
                    "info": [
                        {"countryCodeIso": "DE", "name": "Germany"},
                        {"countryCodeIso": "FR", "name": "France"},
                    ],
                }
            )
        if "country=DE" in str(request.url):
            return _ok({"status": "success", "info": []})
        return httpx.Response(501, json={"status": "error", "message": "Method not implemented"})

    with pytest.raises(UserApiRefusal, match="501") as caught:
        asyncio.run(load_order_shop(_conn(), client=_client(handler)))
    assert "France" in caught.value.message
    assert "Пул Data API" in caught.value.message


def test_owned_russia_and_foreign_and_total_mismatch():
    ru = parse_owned_number(
        {
            "number": "74951270777",
            "status": "on",
            "country": "Russia",
            "description": "Moscow",
            "monthly_fee": 2,
            "currency": "RUB",
            "type": "common",
            "start_date": "2015-01-01 18:14:44",
        }
    )
    mapped = mapper.map_number(ru, inventory_kind=InventoryKind.purchased)
    assert mapped is not None
    assert mapped.provider_number_key == "74951270777"
    assert mapped.msisdn == "74951270777"
    assert mapped.period_price == Decimal(2)
    assert mapped.status_raw == "on"
    assert mapped.date_from == "2015-01-01 18:14:44"
    assert mapped.city_name is None
    foreign = mapper.map_number(
        parse_owned_number(
            {
                "number": "+442045770077",
                "status": "on",
                "country": "United Kingdom",
                "description": "London",
                "monthly_fee": 9,
                "currency": "USD",
            }
        ),
        inventory_kind=InventoryKind.purchased,
    )
    assert foreign is not None
    assert foreign.provider_number_key == "United Kingdom:442045770077"
    assert foreign.msisdn == "442045770077"
    assert foreign.period_price is None
    assert foreign.number_local == "442045770077"
    assert foreign.city_name == "London"
    assert foreign.region_name == "United Kingdom"

    def mismatch(request: httpx.Request) -> httpx.Response:
        return _ok({"status": "success", "info": [], "total": 2})

    with pytest.raises(UserApiError, match="total=2"):
        asyncio.run(_client(mismatch).owned())


def test_owned_failure_does_not_keep_data_api_rows(monkeypatch: pytest.MonkeyPatch):
    number = _data_number("74951234567", "100")

    async def _sync(self, connection, **kwargs):
        return SyncResult(
            fetched=1,
            parsed=1,
            items=[number],
            extra_stats={"integrity": {"total_items": 1}},
        )

    async def _owned(*args, **kwargs):
        raise UserApiError("User API HTTP 401 (/v1/direct_numbers/): no")

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    monkeypatch.setattr("app.providers.novofon.provider.load_owned_numbers", _owned)
    result = asyncio.run(NovofonProvider().sync_purchased_numbers(_conn()))
    assert result.items == []
    assert result.fetched == 0
    assert result.warnings
    assert "не записан" in result.extra_stats["refusal_detail"]


def test_owned_row_replaces_data_api_duplicate(monkeypatch: pytest.MonkeyPatch):
    data = mapper.map_number(
        parser.parse_virtual_item(
            {"id": 9, "virtual_phone_number": "74951234567", "status": "active"}
        ),
        inventory_kind=InventoryKind.purchased,
    )
    assert data is not None

    async def _sync(self, connection, **kwargs):
        return SyncResult(fetched=1, parsed=1, items=[data], extra_stats={"integrity": {"total_items": 1}})

    async def _owned(*args, **kwargs):
        from app.providers.novofon.user_api import OwnedNumbers

        row = mapper.map_number(
            parse_owned_number(
                {
                    "number": "74951234567",
                    "status": "on",
                    "country": "Russia",
                    "monthly_fee": 5,
                    "currency": "RUB",
                }
            ),
            inventory_kind=InventoryKind.purchased,
        )
        assert row is not None
        return OwnedNumbers(raw_count=1, mapped=[row], secret_slot="access_token")

    monkeypatch.setattr(NovofonProvider, "_sync_method", _sync)
    monkeypatch.setattr("app.providers.novofon.provider.load_owned_numbers", _owned)
    result = asyncio.run(NovofonProvider().sync_purchased_numbers(_conn()))
    assert len(result.items) == 1
    assert result.items[0].period_price == Decimal(5)
    assert result.items[0].status_raw == "on"
    assert result.items[0].raw_payload["data_api"]["id"] == 9


def test_user_api_module_has_no_mutating_paths():
    text = Path(user_api_module.__file__).read_text()
    assert "direct_numbers/order" not in text
    assert "direct_numbers/prolong" not in text
    assert "client.post" not in text
    assert "client.put" not in text
    assert "connection.base_url" not in text
