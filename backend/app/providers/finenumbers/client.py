"""Finenumbers PSTN HTTP client (read-only)."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderTransportError
from app.providers.finenumbers import contract
from app.providers.retry import RetryPolicy, TimeoutConfig


class FinenumbersClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig(total_timeout=60, connect_timeout=15, read_timeout=60)
        self.retry = retry or RetryPolicy(max_attempts=6)
        self.base_url = (connection.base_url or contract.EXAMPLE_BASE_URL).rstrip("/") + "/"
        self.api_key = connection.auth_settings.get(contract.AUTH_SETTINGS_KEY) or connection.auth_settings.get(
            "api_key"
        )
        if not self.api_key:
            raise ProviderAuthError(
                f"Finenumbers auth_settings.{contract.AUTH_SETTINGS_KEY} is required (Bearer)"
            )
        # Token bucket tuned to PSTN limit: 5000 req/min (use safe 4800/min)
        self._rate_per_sec = contract.RATE_LIMIT_SAFE_PER_MINUTE / 60.0
        self._max_tokens = min(200.0, contract.RATE_LIMIT_SAFE_PER_MINUTE / 10.0)
        self._tokens = self._max_tokens
        self._updated_at = time.monotonic()
        self._rate_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            timeout = httpx.Timeout(
                self.timeout.total_timeout,
                connect=self.timeout.connect_timeout,
                read=self.timeout.read_timeout,
            )
            self._http = httpx.AsyncClient(timeout=timeout, headers=self._headers())
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

    async def _acquire_token(self) -> None:
        """Wait until a rate-limit token is available (4800/min safe budget)."""
        while True:
            async with self._rate_lock:
                now = time.monotonic()
                elapsed = now - self._updated_at
                if elapsed > 0:
                    self._tokens = min(
                        self._max_tokens, self._tokens + elapsed * self._rate_per_sec
                    )
                    self._updated_at = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                need = (1.0 - self._tokens) / self._rate_per_sec
            await asyncio.sleep(max(need, 0.001))

    async def _get(self, path: str, params: dict[str, Any]) -> RawHttpResult:
        url = urljoin(self.base_url, path.lstrip("/"))
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            try:
                await self._acquire_token()
                client = await self._client()
                start = time.perf_counter()
                response = await client.get(url, params=params)
                elapsed = (time.perf_counter() - start) * 1000
                try:
                    body_json = response.json()
                except Exception:
                    body_json = None

                if response.status_code == 429:
                    retry_after = 1.0
                    if isinstance(body_json, dict):
                        details = (body_json.get("error") or {}).get("details") or {}
                        try:
                            retry_after = float(details.get("retryAfterSec") or 1)
                        except (TypeError, ValueError):
                            retry_after = 1.0
                    await asyncio.sleep(max(retry_after, 0.2))
                    last_exc = ProviderTransportError(
                        f"Finenumbers rate limited: {(response.text or '')[:200]}"
                    )
                    continue

                return RawHttpResult(
                    status_code=response.status_code,
                    body_text=response.text,
                    body_json=body_json,
                    headers=dict(response.headers),
                    elapsed_ms=elapsed,
                    request_url=str(response.url),
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 >= self.retry.max_attempts:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderTransportError(f"Finenumbers transport failed: {last_exc}")

    async def lookup_by_inn(
        self,
        *,
        inn: str = contract.OPERATOR_INN,
        page: int = 1,
        page_size: int = contract.DEFAULT_PAGE_SIZE,
    ) -> RawHttpResult:
        return await self._get(
            contract.BY_INN_PATH,
            {"inn": inn, "page": page, "pageSize": page_size},
        )

    async def lookup_phone(self, phone: str) -> RawHttpResult:
        return await self._get(contract.LOOKUP_PATH, {"phone": phone})

    async def iter_all_ranges_by_inn(
        self,
        *,
        inn: str = contract.OPERATOR_INN,
        page_size: int = contract.DEFAULT_PAGE_SIZE,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate by-inn until hasMore is false. Returns (range rows, envelopes)."""
        from app.providers.progress_emit import emit_progress

        ranges: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        page = 1
        await emit_progress(on_progress, "Finenumbers: by-inn")
        while True:
            raw = await self.lookup_by_inn(inn=inn, page=page, page_size=page_size)
            envelopes.append(raw)
            if raw.status_code >= 400:
                raise ProviderTransportError(
                    f"Finenumbers by-inn HTTP {raw.status_code}: {(raw.body_text or '')[:300]}"
                )
            body = raw.body_json if isinstance(raw.body_json, dict) else {}
            chunk = body.get("data") or []
            if isinstance(chunk, list):
                ranges.extend([r for r in chunk if isinstance(r, dict)])
            meta = body.get("meta") or {}
            await emit_progress(
                on_progress,
                f"Finenumbers: by-inn page {page}",
                len(ranges),
                None,
            )
            if not meta.get("hasMore"):
                break
            page = int(meta.get("page") or page) + 1
        return ranges, envelopes
