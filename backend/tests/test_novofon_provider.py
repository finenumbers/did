"""Unit tests for Novofon Data API client/parser (no live HTTP)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.models.enums import InventoryKind, ProviderCode
from app.modules.pstn_inn_cache.service import REQUIRED_INNS, REQUIRED_OPERATORS
from app.modules.sync_engine.unified import PROVIDER_ORDER
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderParseError
from app.providers.novofon import contract, mapper, parser
from app.providers.novofon.client import NovofonClient, NovofonPrincipal
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
    assert "user_id" not in params
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


def _rpc_error(mnemonic: str, code: int = -32003) -> RawHttpResult:
    return _raw(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "error": {"code": code, "message": mnemonic, "data": {"mnemonic": mnemonic}},
        }
    )


def _account(app_id: int = 15, name: str = "Кабинет") -> RawHttpResult:
    return _raw(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "meta_data": {},
                "data": [{"app_id": app_id, "name": name, "timezone": "Europe/Moscow"}],
            },
        }
    )


def _scripted(handler):
    seen: list[tuple[str, dict]] = []

    async def _call(method, params=None):
        body = dict(params or {})
        seen.append((method, body))
        return handler(method, body)

    return seen, _call


def test_client_key_omits_stored_user_id_and_keeps_auth():
    auth = {"access_token": "token", "user_id": "99"}
    client = NovofonClient(
        ConnectionConfig(base_url="https://example.test/v2.0", auth_settings=auth),
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0),
    )

    def handler(method, params):
        if method == contract.METHOD_CUSTOMER_USERS:
            return _rpc_error("forbidden")
        if method == contract.METHOD_ACCOUNT:
            return _account()
        assert "user_id" not in params
        return _page(0, [])

    seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]

    async def _run():
        principal = await client.resolve_principal()
        await client.get_page(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS, limit=1)
        return principal

    principal = asyncio.run(_run())
    assert principal.kind == "client"
    assert principal.user_id is None
    assert principal.app_id == 15
    assert "user_id=99 не отправлен" in principal.summary
    assert auth["user_id"] == "99"
    assert seen[-1][0] == contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS
    assert "user_id" not in seen[-1][1]


def test_empty_customer_users_with_account_stays_client():
    client = _client()

    def handler(method, params):
        if method == contract.METHOD_CUSTOMER_USERS:
            return _page(0, [])
        if method == contract.METHOD_ACCOUNT:
            return _account(name="Клиент")
        raise AssertionError(method)

    _seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]
    principal = asyncio.run(client.resolve_principal())
    assert principal.kind == "client"
    assert "get.customer_users вернул 0" in principal.summary


def test_agent_sends_only_a_verified_user_id():
    client = _client(user_id="5")

    def handler(method, params):
        if method == contract.METHOD_CUSTOMER_USERS and "filter" not in params:
            return _page(2, [{"id": 5, "name": "Анна", "login": "anna", "customer_id": 8}])
        if method == contract.METHOD_CUSTOMER_USERS:
            assert params["filter"] == {"field": "id", "operator": "=", "value": 5}
            assert isinstance(params["filter"]["value"], int)
            return _page(1, [{"id": 5, "name": "Анна", "login": "anna", "customer_id": 8}])
        assert params["user_id"] == 5
        return _page(1, [{"phone_number": "79001234567"}])

    seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]

    async def _run():
        principal = await client.resolve_principal()
        await client.get_page(contract.METHOD_VIRTUAL_NUMBERS, limit=1)
        return principal

    principal = asyncio.run(_run())
    assert principal.kind == "agent"
    assert principal.user_id == 5
    assert seen[-1][1]["user_id"] == 5


def test_agent_without_user_id_does_not_call_number_methods():
    client = _client()

    def handler(method, params):
        assert method == contract.METHOD_CUSTOMER_USERS
        if params.get("limit") == 1:
            return _page(2, [{"id": 5, "name": "Анна", "login": "anna", "customer_id": 8}])
        return _page(
            2,
            [
                {"id": 5, "name": "Анна", "login": "anna", "customer_id": 8},
                {"id": 6, "name": "Борис", "login": "boris", "customer_id": 9},
            ],
        )

    _seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]
    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.resolve_principal())
    assert exc.value.code == "NOVOFON_AGENT_USER_REQUIRED"
    assert "id=5" in str(exc.value)
    assert "id=6" in str(exc.value)


def test_agent_unknown_user_id_does_not_call_number_methods():
    client = _client(user_id=7)

    def handler(method, params):
        assert method == contract.METHOD_CUSTOMER_USERS
        if "filter" in params:
            return _page(0, [])
        return _page(1, [{"id": 5, "name": "Анна", "login": "anna", "customer_id": 8}])

    _seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]
    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.resolve_principal())
    assert exc.value.code == "NOVOFON_AGENT_USER_REQUIRED"
    assert "user_id=7" in str(exc.value)


def test_invalid_token_does_not_probe_account():
    client = _client()
    seen: list[str] = []

    async def _call(method, params=None):
        seen.append(method)
        return _rpc_error("access_token_invalid", -32001)

    client.call = _call  # type: ignore[method-assign]
    with pytest.raises(ProviderAuthError):
        asyncio.run(client.resolve_principal())
    assert seen == [contract.METHOD_CUSTOMER_USERS]


def test_principal_is_resolved_once_per_provider(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def _resolve(self):
        calls.append("resolve")
        principal = NovofonPrincipal(
            kind="client",
            summary="Клиент «А» app_id=3",
            app_id=3,
            name="А",
        )
        self.adopt_principal(principal)
        return principal

    async def _iter(self, method, *, on_progress=None):
        return [], [], {"method": method, "fetched": 0, "total_items": 0, "limits": {}}

    monkeypatch.setattr(NovofonClient, "resolve_principal", _resolve)
    monkeypatch.setattr(NovofonClient, "iter_all", _iter)
    provider = NovofonProvider()
    connection = ConnectionConfig(
        base_url="https://example.test/v2.0",
        auth_settings={"access_token": "token"},
    )

    async def _run():
        free = await provider.sync_free_numbers(connection)
        purchased = await provider.sync_purchased_numbers(connection)
        return free, purchased

    free, purchased = asyncio.run(_run())
    assert calls == ["resolve"]
    assert free.extra_stats["principal"]["app_id"] == 3
    assert purchased.extra_stats["principal"]["summary"] == "Клиент «А» app_id=3"


def test_connection_reports_failure_without_number_calls():
    provider = NovofonProvider()
    connection = ConnectionConfig(
        base_url="https://example.test/v2.0",
        auth_settings={"access_token": "token"},
    )

    async def _resolve(self):
        raise ProviderError("нужен user_id", code="NOVOFON_AGENT_USER_REQUIRED")

    async def _page(*args, **kwargs):
        raise AssertionError("number method")

    original_resolve = NovofonClient.resolve_principal
    original_page = NovofonClient.get_page
    NovofonClient.resolve_principal = _resolve  # type: ignore[method-assign]
    NovofonClient.get_page = _page  # type: ignore[method-assign]
    try:
        result = asyncio.run(provider.test_connection(connection))
    finally:
        NovofonClient.resolve_principal = original_resolve  # type: ignore[method-assign]
        NovofonClient.get_page = original_page  # type: ignore[method-assign]
    assert result.ok is False
    assert "нужен user_id" in result.message


def test_connection_reads_the_cabinet_and_does_not_call_the_shop():
    import app.providers.novofon.provider as provider_module

    provider = NovofonProvider()
    connection = ConnectionConfig(
        base_url="https://example.test/v2.0",
        auth_settings={"access_token": "token", "api_key": "key", "api_secret": "secret"},
    )
    probed: list[str] = []

    class _Api:
        def __init__(self, connection):
            pass

        async def countries(self):
            raise AssertionError("countries")

        async def directions(self, iso: str):
            raise AssertionError(iso)

        async def owned(self):
            probed.append("owned")
            return [{"number": "74951234567"}]

    async def _resolve(self):
        return NovofonPrincipal(kind="client", app_id=1, name="A", summary="Клиент «A» app_id=1")

    async def _data_page(self, method, **kwargs):
        return _page(0, [])

    original_api = provider_module.NovofonUserApi
    original_resolve = NovofonClient.resolve_principal
    original_page = NovofonClient.get_page
    provider_module.NovofonUserApi = _Api  # type: ignore[misc]
    NovofonClient.resolve_principal = _resolve  # type: ignore[method-assign]
    NovofonClient.get_page = _data_page  # type: ignore[method-assign]
    try:
        result = asyncio.run(provider.test_connection(connection))
    finally:
        provider_module.NovofonUserApi = original_api  # type: ignore[misc]
        NovofonClient.resolve_principal = original_resolve  # type: ignore[method-assign]
        NovofonClient.get_page = original_page  # type: ignore[method-assign]
    assert result.ok is True
    assert "501" not in result.message
    assert "номеров=1" in result.message
    assert probed == ["owned"]
    assert result.details["owned"] == 1


@pytest.mark.parametrize(
    "mnemonic",
    ["component_disabled", "method_component_disabled", "future_component_spelling"],
)
def test_component_miss_on_partner_probe_reads_numbers_as_client(mnemonic: str):
    auth = {"access_token": "token", "user_id": "99"}
    client = NovofonClient(
        ConnectionConfig(base_url="https://example.test/v2.0", auth_settings=auth),
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0),
    )

    def handler(method, params):
        if method == contract.METHOD_CUSTOMER_USERS:
            return _rpc_error(mnemonic, -32008)
        if method == contract.METHOD_ACCOUNT:
            return _account()
        assert "user_id" not in params
        return _page(0, [])

    seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]

    async def _run():
        principal = await client.resolve_principal()
        await client.get_page(contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS, limit=1)
        return principal

    principal = asyncio.run(_run())
    assert principal.kind == "client"
    assert principal.user_id is None
    assert principal.app_id == 15
    assert f"get.customer_users={mnemonic}" in principal.summary
    assert auth["user_id"] == "99"
    assert "user_id" not in seen[-1][1]


def test_component_miss_on_both_probes_still_reads_numbers():
    client = _client(user_id="4")

    def handler(method, params):
        if method == contract.METHOD_CUSTOMER_USERS:
            return _rpc_error("component_disabled", -32008)
        if method == contract.METHOD_ACCOUNT:
            return _rpc_error("component_disabled", -32008)
        assert "user_id" not in params
        return _page(0, [])

    seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]

    async def _run():
        principal = await client.resolve_principal()
        await client.get_page(contract.METHOD_VIRTUAL_NUMBERS, limit=1)
        return principal

    principal = asyncio.run(_run())
    assert principal.kind == "client"
    assert principal.user_id is None
    assert principal.app_id is None
    assert "get.customer_users=component_disabled" in principal.summary
    assert "get.account=component_disabled" in principal.summary
    assert seen[-1][0] == contract.METHOD_VIRTUAL_NUMBERS
    assert "user_id" not in seen[-1][1]


def test_forbidden_on_both_probes_does_not_call_numbers():
    client = _client()

    def handler(method, params):
        if method in (contract.METHOD_CUSTOMER_USERS, contract.METHOD_ACCOUNT):
            return _rpc_error("forbidden")
        raise AssertionError(method)

    _seen, call = _scripted(handler)
    client.call = call  # type: ignore[method-assign]
    with pytest.raises(ProviderError) as exc:
        asyncio.run(client.resolve_principal())
    assert exc.value.code == "NOVOFON_PRINCIPAL_UNKNOWN"


def test_component_disabled_on_number_page_keeps_server_message():
    raw = _raw(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "error": {
                "code": -32008,
                "message": "Component dataapi_agent has been disabled",
                "data": {"mnemonic": "component_disabled"},
            },
        }
    )
    with pytest.raises(ProviderParseError) as exc:
        parser.parse_list_page(raw)
    text = str(exc.value)
    assert "Component dataapi_agent has been disabled" in text
    assert "mnemonic=component_disabled" in text
