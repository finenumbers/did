"""
Runexis Numbering API client (JSON-RPC).
Doc: Runexis-Numbering-API.docx — sole source for free / purchasable catalog.
READ-ONLY: connect + search_numbers (+ count). Never reserv/book/sell/…
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderParseError, ProviderTransportError
from app.providers.progress_emit import ProgressCb, emit_progress
from app.providers.retry import RetryPolicy, TimeoutConfig
from app.providers.runexis import contract

logger = logging.getLogger(__name__)


def _looks_like_number_item(value: dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "phone_number",
            "phoneNumber",
            "full_number",
            "fullNumber",
            "city_code",
            "cityCode",
            "number",
        )
    )


def _chunk_from_search_result(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        inner = result.get("numbers") or result.get("data") or result.get("items")
        if isinstance(inner, list):
            return inner
        if _looks_like_number_item(result):
            return [result]
        raise ProviderParseError(
            "Unexpected Runexis Numbering search_numbers dict shape: "
            f"keys={list(result.keys())[:30]}"
        )
    raise ProviderParseError(
        f"Unexpected Runexis Numbering search_numbers result type: {type(result).__name__}"
    )


def _parse_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, bool):
        raise ProviderParseError(f"Unexpected count boolean: {result!r}")
    if isinstance(result, int):
        return result
    if isinstance(result, float):
        return int(result)
    if isinstance(result, str) and result.strip().isdigit():
        return int(result.strip())
    raise ProviderParseError(f"Unexpected search_numbers_count result: {result!r}")


class RunexisNumberingClient:
    """JSON-RPC client for https://did-api.runexis.ru/ (Numbering API)."""

    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig(
            connect_timeout=contract.NUMBERING_CONNECT_TIMEOUT,
            read_timeout=contract.NUMBERING_READ_TIMEOUT,
            total_timeout=contract.NUMBERING_TOTAL_TIMEOUT,
        )
        self.retry = retry or RetryPolicy()
        auth = connection.auth_settings or {}
        self.login = auth.get(contract.AUTH_NUMBERING_LOGIN)
        self.password = auth.get(contract.AUTH_NUMBERING_PASSWORD)
        self.partition = auth.get(contract.AUTH_NUMBERING_PARTITION)
        self.session_id = auth.get(contract.AUTH_NUMBERING_SESSION)
        base = (
            auth.get(contract.AUTH_NUMBERING_BASE_URL)
            or contract.NUMBERING_EXAMPLE_BASE_URL
        )
        self.base_url = str(base).rstrip("/") + "/"
        self._client: httpx.AsyncClient | None = None
        self._reconnect_lock = asyncio.Lock()
        if not self.login or not self.password:
            raise ProviderAuthError(
                "Runexis Numbering API requires auth_settings.numbering_login and "
                "auth_settings.numbering_password "
                "(VERIFIED: JSON-RPC connect in Runexis-Numbering-API.docx)."
            )

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout())
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _persist_session(self, session_id: str) -> None:
        self.session_id = session_id
        auth = dict(self.connection.auth_settings or {})
        auth[contract.AUTH_NUMBERING_SESSION] = session_id
        self.connection.auth_settings = auth

    async def _post_form(self, form: dict[str, str]) -> RawHttpResult:
        client = await self._get_client()
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            try:
                start = time.perf_counter()
                response = await client.post(
                    self.base_url,
                    data=form,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json, text/plain, */*",
                    },
                )
                elapsed = (time.perf_counter() - start) * 1000
                try:
                    body_json = response.json()
                except Exception:
                    body_json = None
                    if response.text:
                        try:
                            body_json = json.loads(response.text)
                        except Exception:
                            body_json = None
                return RawHttpResult(
                    status_code=response.status_code,
                    body_text=response.text,
                    body_json=body_json,
                    headers=dict(response.headers),
                    elapsed_ms=elapsed,
                    request_url=str(response.request.url),
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 >= self.retry.max_attempts:
                    break
        raise ProviderTransportError(f"Runexis Numbering transport failed: {last_exc}")

    async def rpc(self, method: str, params: list[Any], *, rpc_id: int = 1) -> RawHttpResult:
        envelope = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": rpc_id,
        }
        return await self._post_form({"jsonrpc": json.dumps(envelope, ensure_ascii=False)})

    @staticmethod
    def extract_result(raw: RawHttpResult) -> Any:
        if raw.status_code >= 400:
            raise ProviderTransportError(
                f"Runexis Numbering HTTP {raw.status_code}: {raw.body_text[:300]}"
            )
        body = raw.body_json
        if not isinstance(body, dict):
            raise ProviderAuthError(
                f"Runexis Numbering non-JSON response: {raw.body_text[:300]}"
            )
        if "error" in body and body.get("error") is not None:
            raise ProviderAuthError(f"Runexis Numbering RPC error: {body.get('error')}")
        result = body.get("result")
        if result == "error%" or (
            isinstance(result, str) and result.startswith("error")
        ):
            raise ProviderAuthError(f"Runexis Numbering result error: {result}")
        return result

    async def connect(self) -> str:
        params: list[Any] = [self.login, self.password]
        if self.partition not in (None, ""):
            params.append(self.partition)
        raw = await self.rpc(contract.NUMBERING_METHOD_CONNECT, params, rpc_id=1)
        result = self.extract_result(raw)
        if not isinstance(result, str) or not result:
            raise ProviderAuthError(
                f"Runexis Numbering connect did not return session id: {result!r}"
            )
        self._persist_session(result)
        return result

    async def ensure_session(self) -> str:
        if self.session_id:
            return str(self.session_id)
        async with self._reconnect_lock:
            if self.session_id:
                return str(self.session_id)
            return await self.connect()

    async def search_numbers(
        self,
        filters: dict[str, Any],
        *,
        offset: int,
        limit: int,
    ) -> RawHttpResult:
        session = await self.ensure_session()
        raw = await self.rpc(
            contract.NUMBERING_METHOD_SEARCH,
            [session, filters, offset, limit],
            rpc_id=9,
        )
        try:
            self.extract_result(raw)
            return raw
        except ProviderAuthError:
            async with self._reconnect_lock:
                await self.connect()
                session = str(self.session_id)
            raw2 = await self.rpc(
                contract.NUMBERING_METHOD_SEARCH,
                [session, filters, offset, limit],
                rpc_id=9,
            )
            self.extract_result(raw2)
            return raw2

    async def search_numbers_count(self, filters: dict[str, Any]) -> int:
        session = await self.ensure_session()
        raw = await self.rpc(
            contract.NUMBERING_METHOD_SEARCH_COUNT,
            [session, filters],
            rpc_id=11,
        )
        try:
            result = self.extract_result(raw)
        except ProviderAuthError:
            async with self._reconnect_lock:
                await self.connect()
                session = str(self.session_id)
            raw = await self.rpc(
                contract.NUMBERING_METHOD_SEARCH_COUNT,
                [session, filters],
                rpc_id=11,
            )
            result = self.extract_result(raw)
        return _parse_count(result)

    async def _fetch_page(
        self,
        filters: dict[str, Any],
        *,
        offset: int,
        limit: int,
    ) -> tuple[int, list[Any], RawHttpResult, int]:
        t0 = time.perf_counter()
        raw = await self.search_numbers(filters, offset=offset, limit=limit)
        result = self.extract_result(raw)
        chunk = _chunk_from_search_result(result)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        return offset, chunk, raw, elapsed_ms

    @staticmethod
    def _page_meta(
        *,
        count_hint: int,
        raw_fetched: int,
        sequential_verify: bool,
        final_short_page_offset: int | None,
        page_limit: int,
        concurrency_requested: int,
    ) -> dict[str, Any]:
        gap = max(0, int(count_hint) - int(raw_fetched)) if count_hint else 0
        return {
            "count_hint": int(count_hint or 0),
            "raw_fetched": int(raw_fetched),
            "sequential_verify": bool(sequential_verify),
            "final_short_page_offset": final_short_page_offset,
            "count_hint_gap": gap,
            "page_limit": int(page_limit),
            "concurrency_requested": int(concurrency_requested),
            "count_is_progress_hint": True,
        }

    async def _page_all(
        self,
        filters: dict[str, Any],
        *,
        on_progress: ProgressCb | None = None,
        limit: int | None = None,
        concurrency: int | None = None,
        count_hint: int | None = None,
    ) -> tuple[list[Any], list[RawHttpResult], dict[str, Any]]:
        """
        Paginate search_numbers until a verified short/empty page.

        ``search_numbers_count`` is only a progress upper bound (API total inventory),
        not the free-list size — never fail because fetched < count.
        """
        if count_hint is None:
            await emit_progress(on_progress, "Numbering: запрос count…")
            count_hint = await self.search_numbers_count(filters)
        logger.warning(
            "Runexis Numbering search_numbers_count filter=%s count_hint=%s "
            "(progress only; not free-list size)",
            filters,
            count_hint,
        )
        total_hint = count_hint if count_hint > 0 else None
        await emit_progress(
            on_progress,
            "Numbering: загрузка страницы 1…",
            0,
            total_hint,
        )
        limit = int(limit if limit is not None else contract.NUMBERING_PAGE_LIMIT)
        concurrency_requested = max(
            1,
            int(
                concurrency
                if concurrency is not None
                else contract.NUMBERING_FETCH_CONCURRENCY
            ),
        )
        concurrency = concurrency_requested

        offset0, chunk0, raw0, ms0 = await self._fetch_page(filters, offset=0, limit=limit)
        pages: dict[int, list[Any]] = {0: chunk0}
        last_env = raw0
        logger.warning(
            "Runexis Numbering search_numbers page=1 offset=0 got=%s "
            "total_fetched=%s count_hint=%s limit=%s concurrency=%s ms=%s",
            len(chunk0),
            len(chunk0),
            count_hint,
            limit,
            concurrency,
            ms0,
        )
        if chunk0 and isinstance(chunk0[0], dict):
            logger.warning(
                "Runexis Numbering first item keys=%s",
                list(chunk0[0].keys())[:25],
            )
        await emit_progress(
            on_progress,
            "Numbering: страница 1",
            len(chunk0),
            count_hint if count_hint > 0 else None,
        )

        if not chunk0 or len(chunk0) < limit:
            return (
                chunk0,
                [last_env],
                self._page_meta(
                    count_hint=count_hint,
                    raw_fetched=len(chunk0),
                    sequential_verify=False,
                    final_short_page_offset=0,
                    page_limit=limit,
                    concurrency_requested=concurrency_requested,
                ),
            )

        next_offset = limit
        page_num = 1
        # Parallel waves can truncate early; verify once with sequential re-fetch.
        sequential_resume_used = concurrency <= 1
        final_short_page_offset: int | None = None

        while next_offset <= 5_000_000:
            sem = asyncio.Semaphore(concurrency)

            async def _one(off: int) -> tuple[int, list[Any], RawHttpResult, int]:
                async with sem:
                    return await self._fetch_page(filters, offset=off, limit=limit)

            wave = [next_offset + i * limit for i in range(concurrency)]
            results = await asyncio.gather(
                *[_one(off) for off in wave],
                return_exceptions=True,
            )
            failures = [r for r in results if isinstance(r, BaseException)]
            if failures:
                raise ProviderTransportError(
                    f"Runexis Numbering parallel page failed: {failures[0]}"
                ) from failures[0]

            typed = sorted(
                (r for r in results if not isinstance(r, BaseException)),
                key=lambda row: row[0],
            )
            for off, chunk, raw, elapsed_ms in typed:
                page_num += 1
                pages[off] = chunk
                last_env = raw
                total_fetched = sum(len(c) for c in pages.values())
                logger.warning(
                    "Runexis Numbering search_numbers page=%s offset=%s got=%s "
                    "total_fetched=%s count_hint=%s ms=%s",
                    page_num,
                    off,
                    len(chunk),
                    total_fetched,
                    count_hint,
                    elapsed_ms,
                )
                await emit_progress(
                    on_progress,
                    f"Numbering: страница {page_num}",
                    total_fetched,
                    count_hint if count_hint > 0 else None,
                )

            ordered = sorted(pages.keys())
            first_short: int | None = None
            hole_off: int | None = None
            seen_end = False
            for off in ordered:
                chunk = pages[off]
                short = (not chunk) or (len(chunk) < limit)
                if seen_end:
                    if chunk:
                        hole_off = off
                        break
                elif short:
                    first_short = off
                    seen_end = True

            def _resume_sequential_from(start: int) -> None:
                nonlocal next_offset, concurrency, sequential_resume_used
                for off in [o for o in list(pages.keys()) if o >= start]:
                    del pages[off]
                next_offset = start
                concurrency = 1
                sequential_resume_used = True

            if hole_off is not None and not sequential_resume_used and first_short is not None:
                logger.warning(
                    "Runexis Numbering pagination hole at offset=%s under concurrency; "
                    "resuming sequentially from offset=%s",
                    hole_off,
                    first_short,
                )
                _resume_sequential_from(first_short)
                continue

            if hole_off is not None:
                raise ProviderError(
                    (
                        "Incomplete Runexis Numbering fetch: pagination hole "
                        f"at offset={hole_off} (got data after earlier short page)"
                    ),
                    code="PROVIDER_INCOMPLETE_FETCH",
                    details={"offset": hole_off, "count_hint": count_hint},
                )

            if seen_end:
                final_short_page_offset = first_short
                if not sequential_resume_used and first_short is not None:
                    total_fetched = sum(len(c) for c in pages.values())
                    logger.warning(
                        "Runexis Numbering parallel fetch stopped at offset=%s "
                        "(fetched=%s count_hint=%s); verifying sequentially",
                        first_short,
                        total_fetched,
                        count_hint,
                    )
                    _resume_sequential_from(first_short)
                    continue
                break

            next_offset += concurrency * limit

        items: list[Any] = []
        for off in sorted(pages.keys()):
            chunk = pages[off]
            if not chunk:
                if final_short_page_offset is None:
                    final_short_page_offset = off
                break
            items.extend(chunk)
            if len(chunk) < limit:
                final_short_page_offset = off
                break
        return (
            items,
            [last_env],
            self._page_meta(
                count_hint=count_hint,
                raw_fetched=len(items),
                sequential_verify=sequential_resume_used and concurrency_requested > 1,
                final_short_page_offset=final_short_page_offset,
                page_limit=limit,
                concurrency_requested=concurrency_requested,
            ),
        )

    async def list_all_free_numbers(
        self,
        *,
        on_progress: ProgressCb | None = None,
    ) -> tuple[list[Any], list[RawHttpResult], dict[str, Any]]:
        """
        Paginate free inventory via search_numbers (parallel pages).

        Always opens a fresh session for bulk sync (stale sessions can return tiny pages).
        search_numbers_count is treated as a progress hint only.
        """
        await emit_progress(on_progress, "Numbering: подключение…")
        await self.connect()
        await emit_progress(on_progress, "Numbering: сессия")

        envelopes: list[RawHttpResult] = []
        items: list[Any] = []
        used_filter = dict(contract.NUMBERING_FREE_FILTER_PRIMARY)
        meta: dict[str, Any] = {
            "filter": used_filter,
            "fresh_session": True,
            "concurrency": contract.NUMBERING_FETCH_CONCURRENCY,
            "count_is_progress_hint": True,
        }

        try:
            try:
                items, envelopes, page_meta = await self._page_all(
                    used_filter, on_progress=on_progress
                )
            except (ProviderAuthError, ProviderTransportError) as primary_exc:
                used_filter = dict(contract.NUMBERING_FREE_FILTER_FALLBACK)
                meta["filter"] = used_filter
                meta["primary_filter_error"] = str(primary_exc)
                items, envelopes, page_meta = await self._page_all(
                    used_filter, on_progress=on_progress
                )

            count_hint = int(page_meta.get("count_hint") or 0)
            meta.update(page_meta)
            meta["expected_count"] = count_hint
            meta["fetched"] = len(items)
            # Keep gap aligned with actual assembled list length.
            meta["raw_fetched"] = len(items)
            meta["count_hint_gap"] = max(0, count_hint - len(items)) if count_hint else 0

            if not items:
                raise ProviderError(
                    "Empty Runexis Numbering free fetch",
                    code="PROVIDER_INCOMPLETE_FETCH",
                    details={"count_hint": count_hint, "filter": used_filter},
                )
            if count_hint > 0 and len(items) < count_hint:
                logger.warning(
                    "Runexis Numbering free list fetched=%s < count_hint=%s "
                    "count_hint_gap=%s sequential_verify=%s final_short_page_offset=%s "
                    "(count is API total / progress, not free-only size); accepting",
                    len(items),
                    count_hint,
                    meta.get("count_hint_gap"),
                    meta.get("sequential_verify"),
                    meta.get("final_short_page_offset"),
                )

            await emit_progress(
                on_progress,
                f"Numbering: загружено {len(items)}",
                len(items),
                len(items),
            )
            return items, envelopes, meta
        finally:
            await self.aclose()
