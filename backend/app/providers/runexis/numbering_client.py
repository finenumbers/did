"""
Runexis Numbering API client (JSON-RPC).
Doc: Runexis-Numbering-API.docx — sole source for free / purchasable catalog.
READ-ONLY: connect + search_numbers (+ count). Never reserv/book/sell/…
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderParseError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig
from app.providers.runexis import contract

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, int | None, int | None], Any]


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


async def _emit_progress(
    on_progress: ProgressCb | None,
    detail: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if on_progress is None:
        return
    try:
        result = on_progress(detail, current, total)
        if inspect.isawaitable(result):
            await result  # type: ignore[misc]
    except Exception:
        logger.exception("Runexis Numbering progress callback failed")


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

    async def _page_all(
        self,
        filters: dict[str, Any],
        *,
        on_progress: ProgressCb | None = None,
        limit: int | None = None,
        concurrency: int | None = None,
        expected: int | None = None,
    ) -> tuple[list[Any], list[RawHttpResult], int]:
        from app.modules.sync_engine.safety import fetch_complete_enough

        if expected is None:
            expected = await self.search_numbers_count(filters)
        logger.warning(
            "Runexis Numbering search_numbers_count filter=%s expected=%s",
            filters,
            expected,
        )
        limit = int(limit if limit is not None else contract.NUMBERING_PAGE_LIMIT)
        concurrency = max(
            1,
            int(
                concurrency
                if concurrency is not None
                else contract.NUMBERING_FETCH_CONCURRENCY
            ),
        )

        offset0, chunk0, raw0, ms0 = await self._fetch_page(filters, offset=0, limit=limit)
        pages: dict[int, list[Any]] = {0: chunk0}
        last_env = raw0
        logger.warning(
            "Runexis Numbering search_numbers page=1 offset=0 got=%s "
            "total_fetched=%s expected=%s limit=%s concurrency=%s ms=%s",
            len(chunk0),
            len(chunk0),
            expected,
            limit,
            concurrency,
            ms0,
        )
        if chunk0 and isinstance(chunk0[0], dict):
            logger.warning(
                "Runexis Numbering first item keys=%s",
                list(chunk0[0].keys())[:25],
            )
        await _emit_progress(
            on_progress,
            "Numbering: страница 1",
            len(chunk0),
            expected if expected > 0 else None,
        )

        if not chunk0:
            return [], [last_env], expected

        next_offset = len(chunk0) if len(chunk0) < limit else limit
        page_num = 1
        # When parallel waves stop early vs count, drop trailing short pages and
        # resume sequentially once (API often truncates under concurrency).
        sequential_resume_used = concurrency <= 1

        while next_offset <= 5_000_000:
            if len(chunk0) < limit and page_num == 1 and next_offset == len(chunk0):
                # First page already short — only continue if count says more remain.
                ok, _ = fetch_complete_enough(expected=expected, fetched=len(chunk0))
                if ok or sequential_resume_used:
                    break
                sequential_resume_used = True
                concurrency = 1
                logger.warning(
                    "Runexis Numbering short first page (%s < %s) but count=%s; "
                    "continuing sequentially from offset=%s",
                    len(chunk0),
                    limit,
                    expected,
                    next_offset,
                )

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
                    "total_fetched=%s expected=%s ms=%s",
                    page_num,
                    off,
                    len(chunk),
                    total_fetched,
                    expected,
                    elapsed_ms,
                )
                await _emit_progress(
                    on_progress,
                    f"Numbering: страница {page_num}",
                    total_fetched,
                    expected if expected > 0 else None,
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

            if hole_off is not None and concurrency > 1 and not sequential_resume_used:
                # Parallel race: data after a short page — discard from first short and
                # resume one-by-one from that offset.
                logger.warning(
                    "Runexis Numbering pagination hole at offset=%s under concurrency=%s; "
                    "resuming sequentially from offset=%s",
                    hole_off,
                    concurrency,
                    first_short,
                )
                assert first_short is not None
                for off in [o for o in list(pages.keys()) if o >= first_short]:
                    del pages[off]
                next_offset = first_short
                concurrency = 1
                sequential_resume_used = True
                continue

            if hole_off is not None:
                raise ProviderError(
                    (
                        "Incomplete Runexis Numbering fetch: pagination hole "
                        f"at offset={hole_off} (got data after earlier short page)"
                    ),
                    code="PROVIDER_INCOMPLETE_FETCH",
                    details={
                        "offset": hole_off,
                        "expected": expected,
                    },
                )

            if seen_end:
                total_fetched = sum(len(c) for c in pages.values())
                ok, _ = fetch_complete_enough(expected=expected, fetched=total_fetched)
                if ok or sequential_resume_used or first_short is None:
                    break
                logger.warning(
                    "Runexis Numbering parallel fetch stopped at offset=%s with "
                    "fetched=%s expected=%s; resuming sequentially",
                    first_short,
                    total_fetched,
                    expected,
                )
                for off in [o for o in list(pages.keys()) if o >= first_short]:
                    del pages[off]
                next_offset = first_short
                concurrency = 1
                sequential_resume_used = True
                continue

            next_offset += concurrency * limit

        items: list[Any] = []
        for off in sorted(pages.keys()):
            chunk = pages[off]
            if not chunk:
                break
            items.extend(chunk)
            if len(chunk) < limit:
                break
        return items, [last_env], expected

    async def _fetch_remaining(
        self,
        filters: dict[str, Any],
        *,
        start_offset: int,
        expected: int,
        limit: int,
        on_progress: ProgressCb | None = None,
    ) -> tuple[list[Any], list[RawHttpResult]]:
        """
        Continue listing from start_offset with sequential pages.

        Uneven/short pages do not stop the walk while fetched < expected; only an
        empty page ends the scan (Runexis sometimes truncates large pages early).
        """
        from app.modules.sync_engine.safety import fetch_complete_enough

        items: list[Any] = []
        envelopes: list[RawHttpResult] = []
        off = start_offset
        page_num = 0
        while off <= 5_000_000:
            _off, chunk, raw, elapsed_ms = await self._fetch_page(
                filters, offset=off, limit=limit
            )
            page_num += 1
            envelopes.append(raw)
            if not chunk:
                logger.warning(
                    "Runexis Numbering remaining scan empty at offset=%s "
                    "extra=%s total=%s expected=%s",
                    off,
                    len(items),
                    start_offset + len(items),
                    expected,
                )
                break
            items.extend(chunk)
            total = start_offset + len(items)
            logger.warning(
                "Runexis Numbering remaining page=%s offset=%s got=%s "
                "total_fetched=%s expected=%s ms=%s",
                page_num,
                off,
                len(chunk),
                total,
                expected,
                elapsed_ms,
            )
            await _emit_progress(
                on_progress,
                f"Numbering: догрузка {page_num}",
                total,
                expected if expected > 0 else None,
            )
            off += len(chunk)
            ok, _ = fetch_complete_enough(expected=expected, fetched=total)
            if ok:
                break
            if len(chunk) < limit:
                # Short page but still below count — keep walking from new offset.
                continue
        return items, envelopes

    async def list_all_free_numbers(
        self,
        *,
        on_progress: ProgressCb | None = None,
    ) -> tuple[list[Any], list[RawHttpResult], dict[str, Any]]:
        """
        Paginate free inventory via search_numbers (parallel pages, all-or-nothing).
        Always opens a fresh session for bulk sync (stale sessions can return tiny pages).
        """
        await self.connect()

        envelopes: list[RawHttpResult] = []
        items: list[Any] = []
        used_filter = dict(contract.NUMBERING_FREE_FILTER_PRIMARY)
        meta: dict[str, Any] = {
            "filter": used_filter,
            "fresh_session": True,
            "concurrency": contract.NUMBERING_FETCH_CONCURRENCY,
        }
        expected = 0

        try:
            try:
                items, envelopes, expected = await self._page_all(
                    used_filter, on_progress=on_progress
                )
            except (ProviderAuthError, ProviderTransportError) as primary_exc:
                used_filter = dict(contract.NUMBERING_FREE_FILTER_FALLBACK)
                meta["filter"] = used_filter
                meta["primary_filter_error"] = str(primary_exc)
                items, envelopes, expected = await self._page_all(
                    used_filter, on_progress=on_progress
                )

            meta["expected_count"] = expected
            meta["fetched"] = len(items)

            from app.modules.sync_engine.safety import fetch_complete_enough

            ok, reason = fetch_complete_enough(expected=expected, fetched=len(items))
            if not ok and items:
                # Continue from current offset with smaller pages instead of
                # re-downloading hundreds of thousands of rows from offset 0.
                recovery_limit = int(contract.NUMBERING_PAGE_LIMIT_RECOVERY)
                logger.warning(
                    "Runexis Numbering incomplete after primary fetch "
                    "(fetched=%s expected=%s); continuing from offset=%s limit=%s",
                    len(items),
                    expected,
                    len(items),
                    recovery_limit,
                )
                await _emit_progress(
                    on_progress,
                    f"Numbering: догрузка (стр. по {recovery_limit})",
                    len(items),
                    expected if expected > 0 else None,
                )
                extra, extra_envs = await self._fetch_remaining(
                    used_filter,
                    start_offset=len(items),
                    expected=expected,
                    limit=recovery_limit,
                    on_progress=on_progress,
                )
                meta["recovery_limit"] = recovery_limit
                meta["recovery_extra"] = len(extra)
                if extra:
                    items.extend(extra)
                    envelopes.extend(extra_envs)
                    meta["fetched"] = len(items)
                ok, reason = fetch_complete_enough(expected=expected, fetched=len(items))
            if not ok:
                raise ProviderError(
                    reason or "Incomplete Runexis Numbering fetch",
                    code="PROVIDER_INCOMPLETE_FETCH",
                    details={
                        "expected": expected,
                        "fetched": len(items),
                        "filter": used_filter,
                        "recovery_fetched": meta.get("recovery_fetched"),
                    },
                )
            if expected > 0 and len(items) < expected:
                logger.warning(
                    "Runexis Numbering minor count/list gap: count=%s fetched=%s filter=%s",
                    expected,
                    len(items),
                    used_filter,
                )

            await _emit_progress(
                on_progress,
                f"Numbering: загружено {len(items)}",
                len(items),
                expected if expected > 0 else len(items),
            )
            return items, envelopes, meta
        finally:
            await self.aclose()
