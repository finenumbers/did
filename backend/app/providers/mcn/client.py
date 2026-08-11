"""MCN showcase HTTP client. Docs: mcn-contract.md."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.progress_emit import emit_progress
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries
from app.providers.mcn import contract, parser

logger = logging.getLogger(__name__)


def auth_headers(token: str, mode: str) -> dict[str, str]:
    if mode == contract.AUTH_MODE_RAW:
        return {"Authorization": token, "Accept": "application/json"}
    if mode == contract.AUTH_MODE_X_AUTH:
        return {"X-Auth-Token": token, "Accept": "application/json"}
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


class McnClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
        page_limit: int | None = None,
        auth_header_mode: str | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig()
        self.retry = retry or RetryPolicy()
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        if not raw_base.startswith("http"):
            raw_base = f"https://{raw_base}"
        self.base_url = raw_base.rstrip("/")
        self.page_limit = int(page_limit or contract.DEFAULT_PAGE_LIMIT)
        auth = connection.auth_settings or {}
        self._token = (auth.get(contract.AUTH_API_KEY) or "").strip() or None
        self.auth_header_mode = (
            auth_header_mode
            or auth.get(contract.AUTH_HEADER_MODE)
            or contract.AUTH_MODE_BEARER
        )

    def require_token(self) -> str:
        if not self._token:
            raise ProviderAuthError(
                "MCN api_key (Integrations token) is required in Settings"
            )
        return self._token

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        base = f"{self.base_url}{path}"
        clean: dict[str, Any] = {}
        for k, v in (params or {}).items():
            if v is None:
                continue
            clean[k] = v
        if not clean:
            return base
        return f"{base}?{urlencode(clean, doseq=True)}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        auth_mode: str | None = None,
    ) -> RawHttpResult:
        token = self.require_token()
        mode = auth_mode or self.auth_header_mode
        url = self._url(path, params)
        headers = auth_headers(token, mode)
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                return await client.request(method, url, headers=headers)

        start = time.perf_counter()
        try:
            response = await request_with_retries(
                retry=self.retry,
                label=f"MCN {method} {path}",
                do_request=_once,
            )
        except Exception as exc:
            raise ProviderTransportError(f"MCN {path} transport failed: {exc}") from exc
        elapsed = (time.perf_counter() - start) * 1000
        try:
            body_json = response.json()
        except ValueError:
            body_json = None
        raw = RawHttpResult(
            status_code=response.status_code,
            body_text=response.text,
            body_json=body_json,
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url),
        )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"MCN {path} HTTP {response.status_code}",
                details={"status": response.status_code, "auth_mode": mode},
            )
        if response.status_code == 429:
            raise ProviderTransportError(
                f"MCN {path} rate limited (429)",
                details={"status": 429},
            )
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"MCN {path} HTTP {response.status_code}",
                details={
                    "status": response.status_code,
                    "body": (response.text or "")[:500],
                },
            )
        return raw

    async def probe_auth_mode(self) -> tuple[str, RawHttpResult]:
        """Try auth header modes against countries endpoint; return first OK."""
        last_exc: Exception | None = None
        for mode in contract.AUTH_MODE_CANDIDATES:
            try:
                raw = await self.request(
                    "GET", contract.PATH_COUNTRIES, auth_mode=mode
                )
                self.auth_header_mode = mode
                return mode, raw
            except (ProviderAuthError, ProviderTransportError) as exc:
                last_exc = exc
                continue
        raise ProviderAuthError(
            "MCN auth failed for all header modes "
            f"({', '.join(contract.AUTH_MODE_CANDIDATES)})",
            details={"last_error": str(last_exc) if last_exc else None},
        )

    async def get_countries(self) -> tuple[Any, RawHttpResult]:
        raw = await self.request("GET", contract.PATH_COUNTRIES)
        return raw.body_json, raw

    async def get_regions(self) -> tuple[Any, RawHttpResult]:
        raw = await self.request("GET", contract.PATH_REGIONS)
        return raw.body_json, raw

    async def get_cities(self, *, country_code: int = contract.COUNTRY_CODE_RU) -> tuple[Any, RawHttpResult]:
        raw = await self.request(
            "GET",
            contract.PATH_CITIES,
            params={"countryCode": int(country_code)},
        )
        return raw.body_json, raw

    async def get_numbers_page(
        self,
        *,
        country_code: int = contract.COUNTRY_CODE_RU,
        page_number: int = 1,
        limit_per_page: int | None = None,
        city_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], int | None, RawHttpResult]:
        params: dict[str, Any] = {
            "countryCode": int(country_code),
            "pageNumber": int(page_number),
            "limitPerPage": int(limit_per_page if limit_per_page is not None else self.page_limit),
        }
        if city_id is not None:
            params["cities"] = int(city_id)
        raw = await self.request("GET", contract.PATH_NUMBERS, params=params)
        items, total = parser.extract_numbers_page(raw.body_json)
        return items, total, raw

    async def probe_page_limit(self) -> int:
        """Return largest accepted limitPerPage from probes."""
        best = contract.DEFAULT_PAGE_LIMIT
        for limit in contract.PAGE_LIMIT_PROBES:
            try:
                items, total, _ = await self.get_numbers_page(
                    page_number=1, limit_per_page=limit
                )
                best = limit
                # If API silently caps, still keep requested if we got a page
                _ = items, total
            except (ProviderAuthError, ProviderError):
                raise
            except Exception:
                break
        self.page_limit = best
        return best

    async def iter_numbers_slice(
        self,
        *,
        city_id: int | None = None,
        expected_count: int | None = None,
        on_progress: Callable[..., Any] | None = None,
        label: str = "country",
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        page = 1
        total: int | None = None
        limit = self.page_limit
        await emit_progress(on_progress, f"MCN free {label}")
        while page <= contract.MAX_PAGE_NUMBER:
            page_items, page_total, raw = await self.get_numbers_page(
                page_number=page,
                limit_per_page=limit,
                city_id=city_id,
            )
            envelopes.append(raw)
            if total is None and page_total is not None:
                total = page_total
            if not page_items:
                break
            items.extend(page_items)
            if total is not None and len(items) >= total:
                break
            if len(page_items) < limit and (total is None or len(items) >= (total or 0)):
                break
            page += 1

        meta = {
            "city_id": city_id,
            "label": label,
            "fetched": len(items),
            "total_numbers": total,
            "expected_count": expected_count,
            "pages": page,
            "limit_per_page": limit,
        }
        if total is not None and len(items) < total:
            raise ProviderError(
                (
                    f"MCN slice incomplete {label}: fetched={len(items)} "
                    f"totalNumbers={total}"
                ),
                code="MCN_SLICE_INCOMPLETE",
                details=meta,
            )
        return items, envelopes, meta
