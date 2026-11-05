"""Novofon Data API JSON-RPC client. Docs: novofon-contract.md — read-only get.*."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.novofon import contract, parser
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)


class NovofonClient:
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
        self._page_limit_override = page_limit
        auth = connection.auth_settings or {}
        self._token = (auth.get(contract.AUTH_ACCESS_TOKEN) or "").strip() or None
        user_id = auth.get(contract.AUTH_USER_ID)
        self._user_id: int | None = None
        if user_id is not None and str(user_id).strip() != "":
            try:
                self._user_id = int(user_id)
            except (TypeError, ValueError) as exc:
                raise ProviderAuthError(
                    f"Novofon auth_settings.user_id must be a number, got {user_id!r}"
                ) from exc

    def limit_for(self, method: str) -> int:
        if self._page_limit_override is not None:
            return min(self._page_limit_override, contract.MAX_LIMIT)
        if method == contract.METHOD_VIRTUAL_NUMBERS:
            return contract.PURCHASED_PAGE_LIMIT
        return contract.FREE_PAGE_LIMIT

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
            label=f"Novofon {method}",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        try:
            body_json: Any | None = response.json()
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
                "Novofon access_token is required (API key from the Novofon personal account)"
            )
        return self._token

    def _auth_params(self, token: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {contract.AUTH_ACCESS_TOKEN: token}
        if self._user_id is not None:
            params[contract.AUTH_USER_ID] = self._user_id
        if extra:
            params.update(extra)
        return params

    def _category_filter(
        self, *, category: str | None, category_is_null: bool
    ) -> dict[str, Any] | None:
        if category_is_null:
            return {"field": "category", "operator": "=", "value": None}
        if category is not None:
            return {"field": "category", "operator": "=", "value": category}
        return None

    async def get_page(
        self,
        method: str,
        *,
        offset: int = 0,
        limit: int | None = None,
        category: str | None = None,
        category_is_null: bool = False,
    ) -> RawHttpResult:
        token = self.require_access_token()
        extra: dict[str, Any] = {
            "offset": offset,
            "limit": limit if limit is not None else self.limit_for(method),
        }
        filt = self._category_filter(category=category, category_is_null=category_is_null)
        if filt is not None:
            extra["filter"] = filt
        retried = False
        while True:
            raw = await self.call(method, self._auth_params(token, extra))
            wait = parser.limit_retry_wait(raw)
            if wait is not None and not retried:
                retried = True
                logger.warning("Novofon %s minute limit; sleeping %.0fs", method, wait)
                await asyncio.sleep(wait)
                continue
            return raw

    async def _walk(
        self,
        method: str,
        *,
        category: str | None = None,
        category_is_null: bool = False,
        on_progress: Any | None = None,
        label: str = "",
        reject_over_window: bool = False,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        from app.providers.progress_emit import emit_progress

        limit = self.limit_for(method)
        window = contract.MAX_OFFSET + limit
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        total: int | None = None
        stopped_at_max_offset = False
        stop_reason = "unknown"
        prefix = f"Novofon: {method}{label}"
        await emit_progress(on_progress, prefix)
        while True:
            if offset > contract.MAX_OFFSET:
                stopped_at_max_offset = True
                stop_reason = "max_offset"
                break
            raw = await self.get_page(
                method,
                offset=offset,
                limit=limit,
                category=category,
                category_is_null=category_is_null,
            )
            envelopes.append(raw)
            page_items, page_total = parser.parse_list_page(raw)
            if total is None and page_total is not None:
                total = page_total
            if reject_over_window and total is not None and total > window:
                raise ProviderError(
                    f"Novofon {method}{label} slice exceeds offset window: "
                    f"total_items={total} window={window}",
                    code="NOVOFON_PAGINATION_TRUNCATED",
                    details={
                        "method": method,
                        "category": category,
                        "category_is_null": category_is_null,
                        "total_items": total,
                        "window": window,
                    },
                )
            items.extend(page_items)
            await emit_progress(on_progress, f"{prefix} offset={offset}", len(items), total)
            if not page_items:
                stop_reason = "empty_page"
                break
            offset += len(page_items)
            if total is not None and offset >= total:
                stop_reason = "reached_total"
                break
            if len(page_items) < limit and (total is None or offset >= total):
                stop_reason = "short_page"
                break
            if offset > contract.MAX_OFFSET:
                stopped_at_max_offset = True
                stop_reason = "max_offset"
                break

        integrity: dict[str, Any] = {
            "method": method,
            "category": category,
            "category_is_null": category_is_null,
            "fetched": len(items),
            "total_items": total,
            "stop_reason": stop_reason,
            "stopped_at_max_offset": stopped_at_max_offset,
            "total_items_mismatch": bool(
                total is not None and len(items) < total and not stopped_at_max_offset
            ),
        }
        if total is not None and len(items) < total and (
            stopped_at_max_offset or reject_over_window
        ):
            raise ProviderError(
                f"Novofon {method}{label} truncated: fetched {len(items)} of {total}",
                code="NOVOFON_PAGINATION_TRUNCATED",
                details=integrity,
            )
        if total is not None and len(items) < total:
            logger.warning(
                "Novofon %s%s incomplete: fetched %s of %s (stop_reason=%s); persisting fetched",
                method,
                label,
                len(items),
                total,
                stop_reason,
            )
        return items, envelopes, integrity

    async def iter_all(
        self,
        method: str,
        *,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        """Full read. Partition by category when total_items exceeds one offset window."""
        limit = self.limit_for(method)
        window = contract.MAX_OFFSET + limit
        probe = await self.get_page(method, offset=0, limit=limit)
        _probe_items, probe_total = parser.parse_list_page(probe)
        if probe_total is not None and probe_total > window:
            return await self._iter_by_category(
                method,
                expected_total=probe_total,
                on_progress=on_progress,
            )
        return await self._walk(method, on_progress=on_progress)

    async def _iter_by_category(
        self,
        method: str,
        *,
        expected_total: int,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        categories = (
            contract.FREE_CATEGORIES
            if method == contract.METHOD_AVAILABLE_VIRTUAL_NUMBERS
            else contract.PURCHASED_CATEGORIES
        )
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        slices: list[dict[str, Any]] = []
        for category in (*categories, None):
            label = " category=null" if category is None else f" category={category}"
            part, envs, integrity = await self._walk(
                method,
                category=category,
                category_is_null=category is None,
                on_progress=on_progress,
                label=label,
                reject_over_window=True,
            )
            items.extend(part)
            envelopes.extend(envs)
            slices.append(integrity)
        if len(items) != expected_total:
            raise ProviderError(
                f"Novofon {method} category merge fetched {len(items)} "
                f"of total_items={expected_total}",
                code="NOVOFON_PAGINATION_TRUNCATED",
                details={
                    "method": method,
                    "fetched": len(items),
                    "total_items": expected_total,
                    "slices": slices,
                },
            )
        return (
            items,
            envelopes,
            {
                "method": method,
                "fetched": len(items),
                "total_items": expected_total,
                "stop_reason": "category_partition",
                "stopped_at_max_offset": False,
                "total_items_mismatch": False,
                "partitioned": True,
                "slices": slices,
            },
        )
