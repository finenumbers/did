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
from app.providers.msisdn_split import normalize_phone
from app.providers.novofon import contract, mapper, parser
from app.providers.progress_emit import emit_progress

_DIRECTION_ID = re.compile(r"^[A-Za-z0-9]+$")
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
    russia_missing: bool
    mapped: list[NormalizedNumber] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)
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


def russia_iso(countries: list[dict[str, Any]]) -> str | None:
    """ISO string as the countries payload spelled it. ``None`` when Russia is absent."""
    found: str | None = None
    for row in countries:
        if not isinstance(row, dict) or not isinstance(row.get("countryCodeIso"), str):
            raise UserApiError("countries[].countryCodeIso missing")
        iso = row["countryCodeIso"]
        if not iso.strip():
            raise UserApiError("countries[].countryCodeIso missing")
        if found is None and iso.casefold() == "ru":
            found = iso
    return found


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


def parse_shop_number(row: Any, direction: dict[str, Any]) -> ParsedNumberItem:
    if not isinstance(row, dict) or "number" not in row:
        raise UserApiError("available.numbers[] без поля number")
    currency = _currency(row, direction)
    connect = _fee(row, direction, "connect_fee")
    monthly = _fee(row, direction, "monthly_fee")
    rub = currency is not None and currency.casefold() == "rub"
    phone = normalize_phone(row.get("number"))
    payload = {
        "source": "user_api",
        "number": row.get("number"),
        "user_api_number_id": row.get("id"),
        "direction_id": direction.get("id"),
        "location_name": _as_text(direction.get("name")),
        "area_code": _as_text(direction.get("areaCode")),
        "connect_fee": connect,
        "monthly_fee": monthly,
        "currency": currency,
    }
    return ParsedNumberItem(
        raw_payload=payload,
        provider_number_key=phone,
        msisdn=phone,
        buy_price=parser._parse_price(connect) if rub else None,
        period_price=parser._parse_price(monthly) if rub else None,
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


async def load_order_shop(
    connection: ConnectionConfig,
    *,
    on_progress: Any | None = None,
    client: NovofonUserApi | None = None,
) -> OrderShop:
    """Read every RU direction. A hole in the walk raises; it does not return a partial shop."""
    auth = connection.auth_settings or {}
    if not str(auth.get(contract.AUTH_API_KEY) or "").strip():
        return OrderShop(
            directions=0,
            raw_count=0,
            min_per_direction=None,
            max_per_direction=None,
            secret_slot="",
            russia_missing=False,
            skipped=True,
        )
    api = client or NovofonUserApi(connection)
    try:
        countries = await api.countries()
        iso = russia_iso(countries)
    except UserApiError as exc:
        raise UserApiRefusal(
            f"Витрина заказа не дочитана: {exc}. Пул Data API в этом прогоне не записан."
        ) from exc
    if iso is None:
        return OrderShop(
            directions=0,
            raw_count=0,
            min_per_direction=None,
            max_per_direction=None,
            secret_slot=api.secret_slot,
            russia_missing=True,
        )
    try:
        directions = await api.directions(iso)
    except UserApiError as exc:
        raise UserApiRefusal(
            f"Витрина заказа не дочитана: {exc}. Пул Data API в этом прогоне не записан."
        ) from exc

    prepared: list[tuple[str, dict[str, Any]]] = []
    for direction in directions:
        try:
            direction_id = canonical_direction_id(direction.get("id"))
        except UserApiError as exc:
            name = _as_text(direction.get("name")) or ""
            raise UserApiRefusal(
                f"Витрина заказа не дочитана, направление ({name}): {exc}. "
                "Пул Data API в этом прогоне не записан."
            ) from exc
        prepared.append((direction_id, direction))

    mapped: list[NormalizedNumber] = []
    unmapped: list[dict[str, Any]] = []
    counts: list[int] = []
    total = len(prepared)
    for index, (direction_id, direction) in enumerate(prepared, start=1):
        await emit_progress(on_progress, f"направление {index}/{total}", index, total)
        name = _as_text(direction.get("name")) or ""
        try:
            rows = await api.available_numbers(direction_id)
        except UserApiError as exc:
            raise UserApiRefusal(
                f"Витрина заказа не дочитана, направление {direction_id} ({name}): {exc}. "
                "Пул Data API в этом прогоне не записан."
            ) from exc
        counts.append(len(rows))
        for row in rows:
            try:
                parsed = parse_shop_number(row, direction)
            except UserApiError as exc:
                raise UserApiRefusal(
                    f"Витрина заказа не дочитана, направление {direction_id} ({name}): {exc}. "
                    "Пул Data API в этом прогоне не записан."
                ) from exc
            item = mapper.map_number(parsed, inventory_kind=InventoryKind.free)
            if item is None:
                unmapped.append(parsed.raw_payload)
            else:
                mapped.append(item)
    raw_count = sum(counts)
    return OrderShop(
        directions=total,
        raw_count=raw_count,
        min_per_direction=min(counts) if counts else None,
        max_per_direction=max(counts) if counts else None,
        secret_slot=api.secret_slot,
        russia_missing=False,
        mapped=mapped,
        unmapped=unmapped,
    )
