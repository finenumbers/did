"""Novofon classic User API, read-only order shop.

Host is the constant https://api.novofon.com. The Data API host is never called
from here. Signature matches the official PHP client: base64 of the hex HMAC-SHA1,
not the raw digest. GET only. No order, prolong, or mask scan.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urlencode

import httpx

from app.models.enums import InventoryKind
from app.providers.dto.common import ConnectionConfig
from app.providers.dto.numbers import NormalizedNumber, ParsedNumberItem
from app.providers.errors import ProviderError
from app.providers.msisdn_split import normalize_phone, split_from_parts
from app.providers.novofon import contract, mapper, parser
from app.providers.progress_emit import emit_progress

_DIRECTION_ID = re.compile(r"^[A-Za-z0-9]+$")
_RU_LOOKING = re.compile(r"^7[0-9]{10}$")
_RU_LABELS = frozenset({"ru", "russia", "россия", "russian federation"})
_LIST_TOTAL_KEYS = ("total", "count", "total_items")
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class UserApiError(ProviderError):
    """User API rejected or returned a shape we cannot treat as an empty shop."""


class UserApiRefusal(Exception):
    """Shop was not fully read. Callers turn this into an empty slice refusal."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class OrderShop:
    directions: int
    raw_count: int
    min_per_direction: int | None
    max_per_direction: int | None
    secret_slot: str
    countries: int
    mapped: list[NormalizedNumber] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False


@dataclass
class OwnedNumbers:
    raw_count: int
    mapped: list[NormalizedNumber] = field(default_factory=list)
    secret_slot: str = ""
    skipped: bool = False


def build_query(params: dict[str, str]) -> str:
    """PHP ``http_build_query`` with ``PHP_QUERY_RFC1738``: sorted keys, spaces as ``+``."""
    if not params:
        return ""
    return urlencode(sorted(params.items()), quote_via=quote_plus)


def sign_user_api(method: str, params: dict[str, str], secret: str) -> str:
    query = build_query(params)
    digest = hashlib.md5(query.encode()).hexdigest()
    payload = f"{method}{query}{digest}"
    hex_hmac = hmac.new(secret.encode(), payload.encode(), hashlib.sha1).hexdigest()
    return base64.b64encode(hex_hmac.encode()).decode()


def resolve_hmac_secret(auth: dict[str, Any]) -> tuple[str, str]:
    """Explicit api_secret wins. Otherwise the Data API access_token is the Secret."""
    explicit = str(auth.get(contract.AUTH_API_SECRET) or "").strip()
    if explicit:
        return explicit, "api_secret"
    token = str(auth.get(contract.AUTH_ACCESS_TOKEN) or "").strip()
    if token:
        return token, "access_token"
    raise UserApiError("Нет секрета для подписи User API")


def canonical_direction_id(value: Any) -> str:
    if isinstance(value, bool | float):
        raise UserApiError(f"Негодный id направления: {value!r}")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise UserApiError(f"Негодный id направления: {value!r}")
    if _DIRECTION_ID.fullmatch(text) is None:
        raise UserApiError(f"Негодный id направления: {value!r}")
    return text


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _russia_label(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return value.strip().casefold() in _RU_LABELS


@dataclass
class _Identity:
    provider_number_key: str
    msisdn: str | None
    number_local: str | None
    city_name: str | None
    region_name: str | None
    foreign: bool


def identity_for_number(
    number: Any,
    *,
    country_iso: str | None,
    country_label: str | None,
    place_name: str | None,
) -> _Identity:
    """RU keys stay ``7XXXXXXXXXX``. Other countries keep their own digits.

    A non-RU number whose digits look like a Russian MSISDN gets an empty
    ``msisdn`` so the ABC directory does not assign it a Russian city.
    """
    iso = (country_iso or "").strip()
    label = (country_label or "").strip()
    russia = iso.casefold() == "ru" or (not iso and (_russia_label(label) or not label))
    if russia:
        phone = normalize_phone(number)
        if phone:
            _abc, local = split_from_parts(msisdn=phone)
            return _Identity(phone, phone, local, None, None, False)
        if iso or label:
            raise UserApiError(f"Номер не приводится к 7XXXXXXXXXX: {number!r}")
    digits = _digits(number)
    if not digits:
        raise UserApiError("номер без цифр")
    prefix = iso or label
    if not prefix:
        raise UserApiError(f"Нет страны для номера {number!r}")
    return _Identity(
        provider_number_key=f"{prefix}:{digits}",
        msisdn=None if _RU_LOOKING.fullmatch(digits) else digits,
        number_local=digits,
        city_name=place_name,
        region_name=label or iso,
        foreign=True,
    )


def assert_list_complete(body: dict[str, Any], rows: list[Any]) -> None:
    """Refuse a list when the payload names a total that is not its length."""
    for key in _LIST_TOTAL_KEYS:
        if key not in body or body[key] is None:
            continue
        try:
            expected = int(body[key])
        except (TypeError, ValueError) as exc:
            raise UserApiError(f"{key} не число") from exc
        if expected != len(rows):
            raise UserApiError(f"{key}={expected} не равно числу строк {len(rows)}")


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _currency(row: dict[str, Any], direction: dict[str, Any]) -> str | None:
    own = _as_text(row.get("currency")) if "currency" in row else None
    if own:
        return own
    return _as_text(direction.get("currency"))


def _fee(row: dict[str, Any], direction: dict[str, Any], key: str) -> Any:
    if key in row and row[key] is not None:
        return row[key]
    return direction.get(key)


def parse_shop_number(
    row: Any,
    direction: dict[str, Any],
    *,
    country_iso: str = "RU",
    country_name: str | None = None,
) -> ParsedNumberItem:
    if not isinstance(row, dict) or "number" not in row:
        raise UserApiError("available.numbers[] без поля number")
    currency = _currency(row, direction)
    connect = _fee(row, direction, "connect_fee")
    monthly = _fee(row, direction, "monthly_fee")
    rub = currency is not None and currency.casefold() == "rub"
    place = _as_text(direction.get("name"))
    ident = identity_for_number(
        row.get("number"),
        country_iso=country_iso,
        country_label=country_name,
        place_name=place,
    )
    payload = {
        "source": "user_api",
        "number": row.get("number"),
        "user_api_number_id": row.get("id"),
        "direction_id": direction.get("id"),
        "location_name": place,
        "country_iso": country_iso,
        "country_name": country_name,
        "area_code": _as_text(direction.get("areaCode")),
        "connect_fee": connect,
        "monthly_fee": monthly,
        "currency": currency,
    }
    if ident.foreign:
        payload["foreign_catalog"] = True
        payload["catalog_number_local"] = ident.number_local
    return ParsedNumberItem(
        raw_payload=payload,
        provider_number_key=ident.provider_number_key,
        msisdn=ident.msisdn,
        city_name=ident.city_name,
        region_name=ident.region_name,
        buy_price=parser._parse_price(connect) if rub else None,
        period_price=parser._parse_price(monthly) if rub else None,
    )


def parse_owned_number(row: Any) -> ParsedNumberItem:
    if not isinstance(row, dict) or "number" not in row:
        raise UserApiError("direct_numbers[] без поля number")
    currency = _as_text(row.get("currency"))
    rub = currency is not None and currency.casefold() == "rub"
    country = _as_text(row.get("country"))
    place = _as_text(row.get("description"))
    ident = identity_for_number(
        row.get("number"),
        country_iso=None,
        country_label=country,
        place_name=place,
    )
    payload = dict(row)
    payload["source"] = "user_api_owned"
    if ident.foreign:
        payload["foreign_catalog"] = True
        payload["catalog_number_local"] = ident.number_local
    return ParsedNumberItem(
        raw_payload=payload,
        provider_number_key=ident.provider_number_key,
        msisdn=ident.msisdn,
        city_name=ident.city_name,
        region_name=ident.region_name,
        period_price=parser._parse_price(row.get("monthly_fee")) if rub else None,
        status_raw=_as_text(row.get("status")),
        number_type=_as_text(row.get("type")),
        date_from=_as_text(row.get("start_date")),
    )


def _body_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])[:300]
    text = (response.text or "").strip()
    return text[:300] or f"HTTP {response.status_code}"


class NovofonUserApi:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Sleep | None = None,
        pace_seconds: float = contract.USER_API_PACE_SECONDS,
        now: Clock | None = None,
    ):
        auth = dict(connection.auth_settings or {})
        self._key = str(auth.get(contract.AUTH_API_KEY) or "").strip()
        if not self._key:
            raise UserApiError(contract.KEY_MISSING_MESSAGE)
        self._secret, self.secret_slot = resolve_hmac_secret(auth)
        self.base_url = contract.USER_API_BASE_URL
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self._pace_seconds = pace_seconds
        self._now = now or time.time
        self._remaining: int | None = None
        self._reset: float | None = None
        self._available_sent = 0

    async def countries(self) -> list[dict[str, Any]]:
        body = await self._get(contract.USER_API_COUNTRIES, {"language": contract.USER_API_LANGUAGE})
        info = body.get("info")
        if not isinstance(info, list):
            raise UserApiError("countries.info is not an array")
        rows = []
        for row in info:
            if not isinstance(row, dict) or not isinstance(row.get("countryCodeIso"), str):
                raise UserApiError("countries[].countryCodeIso missing")
            if not row["countryCodeIso"].strip():
                raise UserApiError("countries[].countryCodeIso missing")
            rows.append(row)
        return rows

    async def directions(self, country_iso: str) -> list[dict[str, Any]]:
        body = await self._get(
            contract.USER_API_COUNTRY,
            {"country": country_iso, "language": contract.USER_API_LANGUAGE},
        )
        info = body.get("info")
        if not isinstance(info, list):
            raise UserApiError("country.info is not an array")
        rows: list[dict[str, Any]] = []
        for row in info:
            if not isinstance(row, dict):
                raise UserApiError("country.info содержит не объект")
            rows.append(row)
        return rows

    async def owned(self) -> list[dict[str, Any]]:
        body = await self._get(contract.USER_API_OWNED, {})
        info = body.get("info")
        if not isinstance(info, list):
            raise UserApiError("direct_numbers.info is not an array")
        rows: list[dict[str, Any]] = []
        for row in info:
            if not isinstance(row, dict):
                raise UserApiError("direct_numbers.info содержит не объект")
            rows.append(row)
        assert_list_complete(body, rows)
        return rows

    async def available_numbers(self, direction_id: str) -> list[Any]:
        direction_id = canonical_direction_id(direction_id)
        method = f"{contract.USER_API_AVAILABLE}{direction_id}/"
        body = await self._get(method, {}, pace_available=True)
        if "numbers" not in body:
            raise UserApiError("available.numbers missing")
        numbers = body["numbers"]
        if not isinstance(numbers, list):
            raise UserApiError("available.numbers is not an array")
        self._available_sent += 1
        return numbers

    async def _get(
        self,
        method: str,
        params: dict[str, str],
        *,
        pace_available: bool = False,
    ) -> dict[str, Any]:
        attempt = 0
        while True:
            if attempt == 0:
                await self._before(pace_available)
            try:
                response = await self._request(method, params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 0:
                    attempt = 1
                    continue
                raise UserApiError(f"User API {method}: {exc}") from exc
            self._note_limits(response.headers)
            if response.status_code == 429:
                if attempt == 0:
                    wait = self._reset_wait()
                    if wait is None:
                        raise UserApiError(
                            f"User API лимит ({method}): повтор возможен только при reset в пределах 120 с"
                        )
                    await self._sleep(wait)
                    self._remaining = None
                    attempt = 1
                    continue
                raise UserApiError(f"User API лимит после повтора ({method})")
            return self._parse(response, method)

    async def _request(self, method: str, params: dict[str, str]) -> httpx.Response:
        query = build_query(params)
        signature = sign_user_api(method, params, self._secret)
        url = f"{self.base_url}{method}"
        if query:
            url = f"{url}?{query}"
        timeout = httpx.Timeout(
            connect=contract.USER_API_CONNECT_TIMEOUT,
            read=contract.USER_API_READ_TIMEOUT,
            write=contract.USER_API_READ_TIMEOUT,
            pool=contract.USER_API_CONNECT_TIMEOUT,
        )
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "trust_env": False,
            "follow_redirects": False,
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        async with httpx.AsyncClient(**client_kwargs) as client:
            return await client.get(
                url,
                headers={"Authorization": f"{self._key}:{signature}"},
            )

    def _parse(self, response: httpx.Response, method: str) -> dict[str, Any]:
        if response.status_code in {401, 403}:
            raise UserApiError(
                "User API отклонил авторизацию "
                f"(hmac_secret={self.secret_slot}, {method}): {_body_message(response)}"
            )
        if response.status_code != 200:
            raise UserApiError(
                f"User API HTTP {response.status_code} ({method}): {_body_message(response)}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise UserApiError(f"User API {method}: ответ не JSON") from exc
        if not isinstance(body, dict):
            raise UserApiError(f"User API {method}: ответ не объект")
        if body.get("status") != "success":
            message = body.get("message") or body.get("status") or "error"
            raise UserApiError(f"User API {method}: {message}")
        return body

    async def _before(self, pace_available: bool) -> None:
        if self._remaining == 0:
            await self._wait_for_reset()
            return
        if pace_available and self._available_sent > 0 and self._remaining is None:
            await self._sleep(self._pace_seconds)

    async def _wait_for_reset(self) -> None:
        wait = self._reset_wait()
        if self._reset is not None and self._reset - float(self._now()) <= 0:
            self._remaining = None
            return
        if wait is None:
            raise UserApiError("User API лимит: reset вне окна 120 с")
        await self._sleep(wait)
        self._remaining = None

    def _reset_wait(self) -> float | None:
        if self._reset is None:
            return None
        wait = self._reset - float(self._now())
        if 0 < wait <= contract.USER_API_RETRY_MAX_SECONDS:
            return wait
        return None

    def _note_limits(self, headers: httpx.Headers) -> None:
        raw_remaining = headers.get("x-ratelimit-remaining")
        raw_reset = headers.get("x-ratelimit-reset")
        if raw_remaining is not None:
            try:
                self._remaining = int(raw_remaining)
            except ValueError:
                pass
        if raw_reset is not None:
            try:
                self._reset = float(raw_reset)
            except ValueError:
                pass


def _refuse(message: str) -> UserApiRefusal:
    return UserApiRefusal(
        f"Витрина заказа не дочитана: {message}. Пул Data API в этом прогоне не записан."
    )


async def load_order_shop(
    connection: ConnectionConfig,
    *,
    on_progress: Any | None = None,
    client: NovofonUserApi | None = None,
) -> OrderShop:
    """Read every country and direction. A hole raises; it does not return a partial shop."""
    auth = connection.auth_settings or {}
    if not str(auth.get(contract.AUTH_API_KEY) or "").strip():
        return OrderShop(
            directions=0,
            raw_count=0,
            min_per_direction=None,
            max_per_direction=None,
            secret_slot="",
            countries=0,
            skipped=True,
        )
    api = client or NovofonUserApi(connection)
    try:
        countries = await api.countries()
    except UserApiError as exc:
        raise _refuse(str(exc)) from exc
    if not countries:
        return OrderShop(
            directions=0,
            raw_count=0,
            min_per_direction=None,
            max_per_direction=None,
            secret_slot=api.secret_slot,
            countries=0,
        )

    prepared: list[tuple[str, str | None, str, dict[str, Any]]] = []
    for country in countries:
        iso = country["countryCodeIso"]
        country_name = _as_text(country.get("name"))
        try:
            directions = await api.directions(iso)
        except UserApiError as exc:
            label = country_name or iso
            raise _refuse(f"страна {label}: {exc}") from exc
        for direction in directions:
            name = _as_text(direction.get("name")) or ""
            try:
                direction_id = canonical_direction_id(direction.get("id"))
            except UserApiError as exc:
                raise _refuse(f"страна {country_name or iso}, направление ({name}): {exc}") from exc
            prepared.append((iso, country_name, direction_id, direction))

    mapped: list[NormalizedNumber] = []
    seen: set[str] = set()
    counts: list[int] = []
    total = len(prepared)
    country_total = len(countries)
    for index, (iso, country_name, direction_id, direction) in enumerate(prepared, start=1):
        name = _as_text(direction.get("name")) or ""
        await emit_progress(
            on_progress,
            f"страна {iso} ({country_total}), направление {index}/{total}",
            index,
            total,
        )
        try:
            rows = await api.available_numbers(direction_id)
        except UserApiError as exc:
            raise _refuse(f"направление {direction_id} ({name}): {exc}") from exc
        counts.append(len(rows))
        for row in rows:
            try:
                parsed = parse_shop_number(
                    row, direction, country_iso=iso, country_name=country_name
                )
                item = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
            except UserApiError as exc:
                raise _refuse(f"направление {direction_id} ({name}): {exc}") from exc
            if item is None or not item.provider_number_key:
                raise _refuse(f"направление {direction_id} ({name}): номер без ключа")
            if item.provider_number_key in seen:
                raise _refuse(
                    f"направление {direction_id} ({name}): повтор ключа {item.provider_number_key}"
                )
            seen.add(item.provider_number_key)
            mapped.append(item)
    raw_count = sum(counts)
    return OrderShop(
        directions=total,
        raw_count=raw_count,
        min_per_direction=min(counts) if counts else None,
        max_per_direction=max(counts) if counts else None,
        secret_slot=api.secret_slot,
        countries=country_total,
        mapped=mapped,
    )


async def load_owned_numbers(
    connection: ConnectionConfig,
    *,
    on_progress: Any | None = None,
    client: NovofonUserApi | None = None,
) -> OwnedNumbers:
    """Read GET /v1/direct_numbers/. A bad row raises; it does not return a partial list."""
    auth = connection.auth_settings or {}
    if not str(auth.get(contract.AUTH_API_KEY) or "").strip():
        return OwnedNumbers(raw_count=0, skipped=True)
    api = client or NovofonUserApi(connection)
    await emit_progress(on_progress, "список кабинета")
    rows = await api.owned()
    mapped: list[NormalizedNumber] = []
    seen: set[str] = set()
    for row in rows:
        parsed = parse_owned_number(row)
        item = mapper.map_number(parsed, inventory_kind=InventoryKind.purchased)
        if item is None or not item.provider_number_key:
            raise UserApiError("номер кабинета без ключа")
        if item.provider_number_key in seen:
            raise UserApiError(f"повтор ключа {item.provider_number_key}")
        seen.add(item.provider_number_key)
        mapped.append(item)
    return OwnedNumbers(
        raw_count=len(rows),
        mapped=mapped,
        secret_slot=api.secret_slot,
    )
