"""MCN showcase HTTP client. Docs: mcn-contract.md."""

from __future__ import annotations

import asyncio
import logging
import math
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
        seed_items: list[dict[str, Any]] | None = None,
        seed_total: int | None = None,
        seed_envelope: RawHttpResult | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        """Read one slice.

        A country-wide slice with a known totalNumbers is read in waves of
        MAX_SLICE_CONCURRENCY. City slices stay one page at a time so they do
        not multiply that limit. A short page before the last page, or fewer
        numbers than totalNumbers, raises MCN_SLICE_INCOMPLETE.
        """
        limit = self.page_limit
        accepted: dict[int, list[dict[str, Any]]] = {}
        envelopes_by_page: dict[int, RawHttpResult] = {}
        total: int | None = seed_total
        detail = f"MCN free {label}"

        async def _emit(page_no: int | None = None) -> None:
            fetched = sum(len(accepted[p]) for p in accepted)
            await emit_progress(on_progress, detail, fetched, total)
            if page_no is not None and page_no % 50 == 0:
                logger.info(
                    "MCN free %s page %s numbers %s/%s",
                    label,
                    page_no,
                    fetched,
                    total,
                )

        def _incomplete(fetched: int) -> ProviderError:
            meta = {
                "city_id": city_id,
                "label": label,
                "fetched": fetched,
                "total_numbers": total,
                "expected_count": expected_count,
                "pages": max(accepted) if accepted else 0,
                "limit_per_page": limit,
            }
            return ProviderError(
                (
                    f"MCN slice incomplete {label}: fetched={fetched} "
                    f"totalNumbers={total}"
                ),
                code="MCN_SLICE_INCOMPLETE",
                details=meta,
            )

        async def _fetch(page_no: int) -> tuple[list[dict[str, Any]], RawHttpResult]:
            page_items, page_total, raw = await self.get_numbers_page(
                page_number=page_no,
                limit_per_page=limit,
                city_id=city_id,
            )
            nonlocal total
            if total is None and page_total is not None:
                total = page_total
            return page_items, raw

        async def _accept(page_no: int, page_items: list[dict[str, Any]], raw: RawHttpResult) -> None:
            accepted[page_no] = page_items
            envelopes_by_page[page_no] = raw
            await _emit(page_no)

        def _page_count(known_total: int) -> int:
            if known_total <= 0:
                return 0
            return math.ceil(known_total / limit)

        def _keys(page_items: list[dict[str, Any]]) -> set[str]:
            found: set[str] = set()
            for item in page_items:
                key = parser._pick_msisdn(item)
                if key:
                    found.add(key)
            return found

        def _overlaps(pages: dict[int, list[dict[str, Any]]]) -> bool:
            seen = _keys([item for page_no in accepted for item in accepted[page_no]])
            for page_no in sorted(pages):
                keys = _keys(pages[page_no])
                if seen & keys:
                    return True
                seen |= keys
            return False

        def _expected_len(page_no: int, page_count: int) -> int:
            if page_no < page_count:
                return limit
            return max((total or 0) - (page_no - 1) * limit, 0)

        async def _confirm(
            page_no: int,
            page_count: int,
            page_items: list[dict[str, Any]],
            raw: RawHttpResult,
        ) -> tuple[list[dict[str, Any]], RawHttpResult]:
            expected = _expected_len(page_no, page_count)
            if expected <= 0 or len(page_items) >= expected:
                return page_items, raw
            page_items, raw = await _fetch(page_no)
            if len(page_items) < expected:
                raise _incomplete(sum(len(v) for v in accepted.values()) + len(page_items))
            return page_items, raw

        async def _sequential(start_page: int, page_count: int) -> None:
            for page_no in range(start_page, page_count + 1):
                if page_no in accepted:
                    continue
                if page_no > contract.MAX_PAGE_NUMBER:
                    break
                page_items, raw = await _fetch(page_no)
                page_items, raw = await _confirm(page_no, page_count, page_items, raw)
                await _accept(page_no, page_items, raw)

        async def _waves(page_count: int) -> None:
            next_page = 1
            while next_page <= page_count:
                if next_page in accepted:
                    next_page += 1
                    continue
                wave = list(
                    range(
                        next_page,
                        min(next_page + contract.MAX_SLICE_CONCURRENCY, page_count + 1),
                    )
                )
                fetched = await asyncio.gather(
                    *[_fetch(page_no) for page_no in wave],
                    return_exceptions=True,
                )
                good: dict[int, tuple[list[dict[str, Any]], RawHttpResult]] = {}
                rate_limited = False
                for page_no, result in zip(wave, fetched, strict=True):
                    if isinstance(result, ProviderTransportError) and (
                        (result.details or {}).get("status") == 429 or "429" in str(result)
                    ):
                        rate_limited = True
                        continue
                    if isinstance(result, BaseException):
                        raise result
                    good[page_no] = result
                good_pages = {page_no: pair[0] for page_no, pair in good.items()}
                overlapped = _overlaps(good_pages)
                if overlapped:
                    logger.info(
                        "MCN free %s overlapping pages %s; reading the rest one by one",
                        label,
                        wave,
                    )
                    await _sequential(wave[0], page_count)
                    return
                if rate_limited:
                    logger.info(
                        "MCN free %s rate limited on pages %s; reading the rest one by one",
                        label,
                        wave,
                    )
                    for page_no, (page_items, raw) in good.items():
                        page_items, raw = await _confirm(page_no, page_count, page_items, raw)
                        await _accept(page_no, page_items, raw)
                    missing = [page_no for page_no in wave if page_no not in accepted]
                    await _sequential(min(missing) if missing else wave[-1] + 1, page_count)
                    return
                repaired: dict[int, tuple[list[dict[str, Any]], RawHttpResult]] = {}
                for page_no, (page_items, raw) in good.items():
                    page_items, raw = await _confirm(page_no, page_count, page_items, raw)
                    repaired[page_no] = (page_items, raw)
                repaired_pages = {page_no: pair[0] for page_no, pair in repaired.items()}
                if _overlaps(repaired_pages):
                    logger.info(
                        "MCN free %s overlapping pages %s; reading the rest one by one",
                        label,
                        wave,
                    )
                    await _sequential(wave[0], page_count)
                    return
                for page_no, (page_items, raw) in repaired.items():
                    await _accept(page_no, page_items, raw)
                next_page = wave[-1] + 1

        if seed_items is not None:
            if seed_envelope is not None:
                envelopes_by_page[1] = seed_envelope
            accepted[1] = list(seed_items)
            if total is None:
                total = seed_total
        elif city_id is not None:
            pass
        else:
            page_items, raw = await _fetch(1)
            await _accept(1, page_items, raw)

        await _emit()
        use_waves = city_id is None and total is not None
        if use_waves:
            page_count = _page_count(int(total or 0))
            if (
                1 in accepted
                and page_count >= 1
                and len(accepted[1]) < _expected_len(1, page_count)
            ):
                raw = envelopes_by_page.get(1)
                if raw is None:
                    page_items, raw = await _fetch(1)
                else:
                    page_items = accepted[1]
                page_items, raw = await _confirm(1, page_count, page_items, raw)
                await _accept(1, page_items, raw)
            if page_count > 0:
                await _waves(page_count)
        else:
            page = 2 if 1 in accepted else 1
            while page <= contract.MAX_PAGE_NUMBER:
                page_items, raw = await _fetch(page)
                if not page_items:
                    break
                await _accept(page, page_items, raw)
                fetched_now = sum(len(accepted[p]) for p in accepted)
                if total is not None and fetched_now >= total:
                    break
                if len(page_items) < limit and (total is None or fetched_now >= (total or 0)):
                    break
                page += 1

        ordered_pages = sorted(accepted)
        items = [item for page_no in ordered_pages for item in accepted[page_no]]
        envelopes = [envelopes_by_page[page_no] for page_no in ordered_pages if page_no in envelopes_by_page]
        meta = {
            "city_id": city_id,
            "label": label,
            "fetched": len(items),
            "total_numbers": total,
            "expected_count": expected_count,
            "pages": ordered_pages[-1] if ordered_pages else 0,
            "limit_per_page": limit,
        }
        if total is not None and len(items) < total:
            raise _incomplete(len(items))
        return items, envelopes, meta
