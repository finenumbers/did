"""Twilio GET-only client. Never POST IncomingPhoneNumbers or any mutate."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries
from app.providers.twilio import contract
from app.providers.twilio.parser import CountryRow, parse_country

logger = logging.getLogger(__name__)

PageProgress = Callable[[int, int | None], None]


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = (response.headers.get("Retry-After") or "").strip()
    try:
        seconds = float(raw)
    except ValueError:
        return contract.RATE_LIMIT_FALLBACK_SECONDS
    return min(max(seconds, 0.0), contract.RATE_LIMIT_MAX_WAIT_SECONDS)


class TwilioClient:
    def __init__(self, connection: ConnectionConfig):
        self.connection = connection
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        self.base_url = raw_base.rstrip("/")
        extra = connection.extra_settings or {}
        self.pricing_base_url = (
            str(extra.get("pricing_base_url") or "").strip() or contract.PRICING_BASE_URL
        ).rstrip("/")
        auth = connection.auth_settings or {}
        self._account_sid = (auth.get(contract.AUTH_ACCOUNT_SID) or "").strip() or None
        self._auth_token = (auth.get(contract.AUTH_AUTH_TOKEN) or "").strip() or None
        if not self._account_sid or not self._auth_token:
            raise ProviderAuthError(
                "Twilio Account SID / Auth Token missing (Settings → Twilio)",
                details={"code": "TWILIO_AUTH_MISSING"},
            )
        self.timeout = TimeoutConfig(read_timeout=60.0, total_timeout=90.0)
        self.retry = RetryPolicy(
            retry_on_status=list(contract.RETRY_ON_STATUS),
            backoff_seconds=1.5,
        )
        self._http: httpx.AsyncClient | None = None

    def _auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(self._account_sid or "", self._auth_token or "")

    def _http_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

    async def open(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._http_timeout(), auth=self._auth())

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _abs(self, base: str, path: str) -> str:
        if path.startswith("http"):
            return path
        return urljoin(base.rstrip("/") + "/", path.lstrip("/"))

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.open()
        assert self._http is not None
        await asyncio.sleep(contract.REQUEST_GAP_SECONDS)

        async def _do() -> httpx.Response:
            return await self._http.get(url, params=params)

        label = f"Twilio GET {url}"
        response = await request_with_retries(retry=self.retry, label=label, do_request=_do)
        for _ in range(contract.RATE_LIMIT_RETRY_ROUNDS):
            if response.status_code != 429:
                break
            delay = _retry_after_seconds(response)
            logger.warning(
                "%s throttled (429, Twilio-Concurrent-Requests=%s); waiting %.1fs",
                label,
                response.headers.get("Twilio-Concurrent-Requests"),
                delay,
            )
            await asyncio.sleep(delay)
            response = await request_with_retries(retry=self.retry, label=label, do_request=_do)
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"Twilio auth failed HTTP {response.status_code}",
                details={"status": response.status_code, "url": url},
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Twilio GET failed HTTP {response.status_code}",
                details={"status": response.status_code, "body": response.text[:500], "url": url},
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise ProviderTransportError(f"Twilio non-JSON response for {url}") from exc
        if not isinstance(payload, dict):
            raise ProviderError("Twilio response is not a JSON object")
        return payload

    async def list_countries(self, on_page: PageProgress | None = None) -> list[CountryRow]:
        path = contract.PATH_AVAILABLE_COUNTRIES.format(account_sid=self._account_sid)
        url: str | None = self._abs(self.base_url, path)
        params: dict[str, Any] | None = {"PageSize": contract.PAGE_SIZE}
        rows: list[CountryRow] = []
        seen: set[str] = set()
        pages = 0
        while url:
            pages += 1
            if pages > contract.MAX_PAGES:
                raise ProviderError(
                    "Twilio countries pagination exceeded MAX_PAGES",
                    details={"code": "TWILIO_SLICE_INCOMPLETE", "pages": pages},
                )
            payload = await self._get(url, params)
            params = None
            batch = payload.get(contract.COUNTRIES_KEY) or []
            if not isinstance(batch, list):
                raise ProviderError("Twilio countries payload is not a list")
            for item in batch:
                if not isinstance(item, dict):
                    continue
                parsed = parse_country(item)
                if parsed is None or parsed.country_iso in seen:
                    continue
                seen.add(parsed.country_iso)
                rows.append(parsed)
            if on_page is not None:
                on_page(len(rows), None)
            next_url = payload.get("next_page_url") or payload.get("next_page_uri")
            url = str(next_url).strip() if next_url else None
            if url and url.startswith("/"):
                url = self._abs("https://api.twilio.com", url)
            if not batch:
                break
        return rows

    async def fetch_pricing(self, country_iso: str) -> dict[str, Any] | None:
        path = contract.PATH_PRICING_COUNTRY.format(country_code=country_iso)
        url = self._abs(self.pricing_base_url, path)
        try:
            payload = await self._get(url)
        except ProviderError as exc:
            details = exc.details or {}
            if details.get("status") == 404:
                return None
            logger.warning("Twilio pricing miss for %s: %s", country_iso, exc)
            return None
        if not payload.get("iso_country") and not payload.get("phone_number_prices"):
            return None
        return payload

    async def search_available(
        self,
        *,
        country_iso: str,
        number_type: str,
        in_region: str | None = None,
        in_locality: str | None = None,
        area_code: str | None = None,
        contains: str | None = None,
    ) -> list[dict[str, Any]]:
        type_path = contract.SEARCH_TYPE_PATHS.get(number_type)
        if not type_path:
            raise ProviderError(
                f"Unknown Twilio number type: {number_type}",
                details={"code": "TWILIO_UNKNOWN_TYPE"},
            )
        path = contract.PATH_AVAILABLE_TYPE.format(
            account_sid=self._account_sid,
            country_code=country_iso,
            type_path=type_path,
        )
        params = contract.available_search_params(
            country_iso=country_iso,
            in_region=in_region,
            in_locality=in_locality,
            area_code=area_code,
            contains=contains,
        )
        payload = await self._get(self._abs(self.base_url, path), params or None)
        rows = payload.get(contract.AVAILABLE_NUMBERS_KEY) or []
        if not isinstance(rows, list):
            raise ProviderError("Twilio available numbers payload is not a list")
        return [row for row in rows if isinstance(row, dict)]
