"""Exolve Numbering API client — GetList + GetFree only (read-only)."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.exolve import contract
from app.providers.progress_emit import ProgressCb, emit_progress
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)


class ExolveClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
        page_limit: int | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig(read_timeout=90.0, total_timeout=120.0)
        self.retry = retry or RetryPolicy(retry_on_status=[429, 502, 503, 504])
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        self.base_url = raw_base.rstrip("/")
        self.page_limit = int(page_limit or contract.DEFAULT_PAGE_LIMIT)
        auth = connection.auth_settings or {}
        self._api_key = (auth.get(contract.AUTH_API_KEY) or "").strip() or None
        if not self._api_key:
            raise ProviderAuthError(
                "Exolve API key missing (Settings → Exolve → API-ключ)",
                details={"code": "EXOLVE_API_KEY_MISSING"},
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, path: str, body: dict[str, Any]) -> RawHttpResult:
        url = f"{self.base_url}{path}"
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )
        t0 = time.perf_counter()

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.post(url, json=body, headers=self._headers())

        response = await request_with_retries(
            retry=self.retry, label=f"Exolve {path}", do_request=_once
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        text = response.text
        try:
            payload = response.json()
        except Exception:
            payload = None
        raw = RawHttpResult(
            status_code=response.status_code,
            body_text=text[:4000],
            body_json=payload,
            headers=dict(response.headers),
            elapsed_ms=elapsed_ms,
            request_url=url,
        )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"Exolve auth failed HTTP {response.status_code}",
                details={"status": response.status_code, "hint": "EXOLVE_AUTH_FAILED"},
            )
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"Exolve {path} HTTP {response.status_code}: {text[:300]}",
                code="EXOLVE_HTTP_ERROR",
                details={"status": response.status_code, "path": path},
            )
        return raw

    async def get_reference(self) -> tuple[dict[str, Any], RawHttpResult]:
        raw = await self._post(contract.PATH_REFERENCE, {})
        data = raw.body_json if isinstance(raw.body_json, dict) else {}
        return data, raw

    async def get_free_page(
        self,
        *,
        type_id: int,
        region_id: int,
        offset: int,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], RawHttpResult]:
        body: dict[str, Any] = {
            "type_id": int(type_id),
            "region_id": int(region_id),
            "limit": int(limit if limit is not None else self.page_limit),
            "offset": int(offset),
            "random": False,
        }
        raw = await self._post(contract.PATH_GET_FREE, body)
        data = raw.body_json if isinstance(raw.body_json, dict) else {}
        numbers = data.get("numbers")
        if numbers is None:
            numbers = []
        if not isinstance(numbers, list):
            raise ProviderError(
                "Exolve GetFree: numbers is not a list",
                code="EXOLVE_BAD_RESPONSE",
            )
        items = [n for n in numbers if isinstance(n, dict)]
        return items, raw

    async def iter_free_slice(
        self,
        *,
        type_id: int,
        region_id: int,
        on_progress: ProgressCb | None = None,
        type_label: str = "",
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate one (type_id, region_id) slice until short/empty page."""
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        page_limit = self.page_limit
        while offset <= contract.MAX_OFFSET:
            await emit_progress(
                on_progress,
                f"Exolve GetFree {type_label or type_id} region={region_id} offset={offset}",
                len(items),
                None,
            )
            page, raw = await self.get_free_page(
                type_id=type_id, region_id=region_id, offset=offset, limit=page_limit
            )
            envelopes.append(raw)
            if not page:
                break
            items.extend(page)
            if len(page) < page_limit:
                break
            offset += len(page)
            if offset > contract.MAX_OFFSET:
                raise ProviderError(
                    (
                        "Exolve GetFree pagination truncated "
                        f"type_id={type_id} region_id={region_id} offset={offset}"
                    ),
                    code="EXOLVE_PAGINATION_TRUNCATED",
                    details={
                        "type_id": type_id,
                        "region_id": region_id,
                        "offset": offset,
                        "max_offset": contract.MAX_OFFSET,
                    },
                )
        return items, envelopes
