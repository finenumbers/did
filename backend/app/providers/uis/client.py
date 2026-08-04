"""UIS Data API JSON-RPC client. Docs: uis-contract.md — read-only get.*; auth via access_token."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries
from app.providers.uis import contract

logger = logging.getLogger(__name__)


class UisClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
        page_limit: int | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig()
        self.retry = retry or RetryPolicy()
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        self.base_url = raw_base.rstrip("/")
        self.page_limit = min(page_limit or contract.DEFAULT_LIMIT, contract.MAX_LIMIT)
        auth = connection.auth_settings or {}
        self._token = (auth.get(contract.AUTH_ACCESS_TOKEN) or "").strip() or None
        user_id = auth.get(contract.AUTH_USER_ID)
        self._user_id: int | None = None
        if user_id is not None and str(user_id).strip() != "":
            try:
                self._user_id = int(user_id)
            except (TypeError, ValueError) as exc:
                raise ProviderAuthError(
                    f"UIS auth_settings.user_id must be a number, got {user_id!r}"
                ) from exc

    async def call(self, method: str, params: dict[str, Any] | None = None) -> RawHttpResult:
        envelope = {
            "jsonrpc": contract.JSONRPC_VERSION,
            "id": str(uuid.uuid4()),
            "method": method,
            "params": {k: v for k, v in (params or {}).items() if v is not None},
        }
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                return await client.post(
                    self.base_url,
                    json=envelope,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                )

        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label=f"UIS {method}",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        body_json: Any | None
        try:
            body_json = response.json()
        except ValueError:
            body_json = None
        return RawHttpResult(
            status_code=response.status_code,
            body_text=response.text,
            body_json=body_json,
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url),
        )

    def require_access_token(self) -> str:
        if not self._token:
            raise ProviderAuthError(
                "UIS access_token is required (API key from UIS personal account)"
            )
        return self._token

    def _auth_params(self, token: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {contract.AUTH_ACCESS_TOKEN: token}
        if self._user_id is not None:
            params[contract.AUTH_USER_ID] = self._user_id
        if extra:
            params.update(extra)
        return params

    async def get_page(
        self,
        method: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> RawHttpResult:
        token = self.require_access_token()
        return await self.call(
            method,
            self._auth_params(
                token,
                {
                    "offset": offset,
                    "limit": limit if limit is not None else self.page_limit,
                },
            ),
        )

    async def iter_all(
        self,
        method: str,
        *,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate until offset >= total_items or short page.

        Fail closed if API reports more rows than we can fetch within MAX_OFFSET.
        """
        from app.providers.uis.parser import parse_list_page

        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        total: int | None = None
        while offset <= contract.MAX_OFFSET:
            raw = await self.get_page(method, offset=offset, limit=self.page_limit)
            envelopes.append(raw)
            page_items, page_total = parse_list_page(raw)
            if total is None and page_total is not None:
                total = page_total
            items.extend(page_items)
            if on_progress:
                try:
                    on_progress(
                        f"UIS {method} offset={offset}",
                        len(items),
                        total,
                    )
                except Exception:
                    logger.exception("UIS on_progress failed")
            if not page_items:
                break
            offset += len(page_items)
            if total is not None and offset >= total:
                break
            if len(page_items) < self.page_limit:
                break
            if offset > contract.MAX_OFFSET:
                break

        if total is not None and len(items) < total:
            raise ProviderError(
                f"UIS {method} truncated: fetched {len(items)} of {total} "
                f"(MAX_OFFSET={contract.MAX_OFFSET})",
                code="UIS_PAGINATION_TRUNCATED",
                details={
                    "method": method,
                    "fetched": len(items),
                    "total_items": total,
                    "max_offset": contract.MAX_OFFSET,
                },
            )
        return items, envelopes
