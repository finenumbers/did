"""Finenumbers REG HTTP client — read-only GET /api/phones (Contour C)."""

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


class FinenumbersRegClient:
    """Machine API against reg.finenumbers.com. Never calls mutating endpoints."""

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig(
            total_timeout=60, connect_timeout=15, read_timeout=60
        )
        self.retry = retry or RetryPolicy(max_attempts=6)
        extra = connection.extra_settings or {}
        base = (
            extra.get(contract.REG_BASE_URL_EXTRA_KEY)
            or contract.REG_EXAMPLE_BASE_URL
        )
        self.base_url = str(base).rstrip("/") + "/"
        self.api_key = connection.auth_settings.get(contract.REG_AUTH_SETTINGS_KEY)
        if not self.api_key:
            raise ProviderAuthError(
                f"Finenumbers auth_settings.{contract.REG_AUTH_SETTINGS_KEY} is required "
                "(REG Bearer / X-Api-Key)"
            )
        self._rate_per_sec = contract.REG_RATE_LIMIT_SAFE_PER_MINUTE / 60.0
        self._max_tokens = min(200.0, contract.REG_RATE_LIMIT_SAFE_PER_MINUTE / 10.0)
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
                    await asyncio.sleep(0.5 * (attempt + 1))
                    last_exc = ProviderTransportError(
                        f"Finenumbers REG rate limited: {(response.text or '')[:200]}"
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
        raise ProviderTransportError(f"Finenumbers REG transport failed: {last_exc}")

    async def list_phones_page(
        self,
        *,
        kind: str,
        page: int = 1,
        page_size: int = contract.REG_DEFAULT_PAGE_SIZE,
    ) -> RawHttpResult:
        size = min(max(1, page_size), contract.REG_MAX_PAGE_SIZE)
        return await self._get(
            contract.REG_PHONES_PATH,
            {"kind": kind, "page": page, "pageSize": size},
        )

    async def iter_all_endpoint_numbers(
        self,
        *,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate endpoint kinds; return raw phone items with endpointNumber set."""
        from app.providers.progress_emit import emit_progress

        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        seen_ids: set[str] = set()
        await emit_progress(on_progress, "Finenumbers REG: phones")
        for kind in contract.REG_PHONE_KINDS:
            page = 1
            while True:
                raw = await self.list_phones_page(
                    kind=kind, page=page, page_size=contract.REG_MAX_PAGE_SIZE
                )
                envelopes.append(raw)
                if raw.status_code >= 400:
                    raise ProviderTransportError(
                        f"Finenumbers REG phones HTTP {raw.status_code} kind={kind}: "
                        f"{(raw.body_text or '')[:300]}"
                    )
                body = raw.body_json if isinstance(raw.body_json, dict) else {}
                chunk = body.get("items") or []
                if isinstance(chunk, list):
                    for row in chunk:
                        if not isinstance(row, dict):
                            continue
                        ep = row.get("endpointNumber")
                        if not ep:
                            continue
                        rid = str(row.get("id") or "")
                        if rid and rid in seen_ids:
                            continue
                        if rid:
                            seen_ids.add(rid)
                        items.append(row)
                total = int(body.get("total") or 0)
                page_size = int(body.get("pageSize") or contract.REG_MAX_PAGE_SIZE)
                await emit_progress(
                    on_progress,
                    f"Finenumbers REG: {kind} page {page}",
                    len(items),
                    total if total else None,
                )
                if page * page_size >= total or not chunk:
                    break
                page += 1
        return items, envelopes
