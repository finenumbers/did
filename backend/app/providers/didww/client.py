"""DIDWW JSON:API GET-only client. Never POST/PATCH/DELETE."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.didww import contract, parser
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)

PageProgress = Callable[[int, int | None], None]


def _retry_after_seconds(response: httpx.Response) -> float:
    raw = (response.headers.get("Retry-After") or "").strip()
    try:
        seconds = float(raw)
    except ValueError:
        return contract.RATE_LIMIT_FALLBACK_SECONDS
    return min(max(seconds, 0.0), contract.RATE_LIMIT_MAX_WAIT_SECONDS)


class DidwwClient:
    def __init__(self, connection: ConnectionConfig):
        self.connection = connection
        raw_base = (connection.base_url or "").strip() or contract.EXAMPLE_BASE_URL
        self.base_url = raw_base.rstrip("/")
        auth = connection.auth_settings or {}
        self._api_key = (auth.get(contract.AUTH_API_KEY) or "").strip() or None
        if not self._api_key:
            raise ProviderAuthError(
                "DIDWW API key missing (Settings → DIDWW → API-ключ)",
                details={"code": "DIDWW_API_KEY_MISSING"},
            )
        self.timeout = TimeoutConfig(read_timeout=90.0, total_timeout=120.0)
        self.retry = RetryPolicy(
            retry_on_status=list(contract.RETRY_ON_STATUS),
            backoff_seconds=1.5,
        )
        self._http: httpx.AsyncClient | None = None
        self._last_request_at = 0.0

    def _headers(self) -> dict[str, str]:
        return {
            contract.API_KEY_HEADER: self._api_key or "",
            "Accept": contract.ACCEPT,
            "Content-Type": contract.CONTENT_TYPE,
            contract.API_VERSION_HEADER: contract.API_VERSION,
        }

    def _http_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

    async def open(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._http_timeout())

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _throttle(self) -> None:
        await asyncio.sleep(contract.REQUEST_GAP_SECONDS)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.open()
        assert self._http is not None
        url = path if path.startswith("http") else urljoin(self.base_url + "/", path.lstrip("/"))
        await self._throttle()

        async def _do() -> httpx.Response:
            return await self._http.get(url, headers=self._headers(), params=params)

        label = f"DIDWW GET {path}"
        response = await request_with_retries(retry=self.retry, label=label, do_request=_do)
        # 20 rps per API key: respect Retry-After before giving up on a throttled call.
        for _ in range(contract.RATE_LIMIT_RETRY_ROUNDS):
            if response.status_code != 429:
                break
            delay = _retry_after_seconds(response)
            logger.warning("%s throttled (429); waiting %.1fs", label, delay)
            await asyncio.sleep(delay)
            response = await request_with_retries(retry=self.retry, label=label, do_request=_do)
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"DIDWW auth failed HTTP {response.status_code}",
                details={"status": response.status_code, "url": url},
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"DIDWW GET {path} failed HTTP {response.status_code}",
                details={"status": response.status_code, "body": response.text[:500]},
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise ProviderTransportError(f"DIDWW non-JSON response for {path}") from exc
        if not isinstance(payload, dict):
            raise ProviderError("DIDWW response is not a JSON object")
        return payload

    async def get_once(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._get(path, params)

    async def iter_collection(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        page_size: int | None = None,
        paginated: bool = True,
        label: str | None = None,
        on_page: PageProgress | None = None,
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        """Walk a JSON:API collection.

        DIDWW returns only `links.first` / `links.last`, never `links.next`, so paging is
        driven by `meta.total_records` with a full-page fallback when meta is absent.
        """
        query = dict(params or {})
        items: list[dict[str, Any]] = []
        idx: dict[tuple[str, str], dict[str, Any]] = {}
        seen: set[tuple[str, str]] = set()
        name = label or path.strip("/")
        size = page_size if (paginated and page_size) else None
        total: int | None = None
        last_page: int | None = None
        page = 1
        while True:
            page_query = dict(query)
            if size:
                page_query["page[size]"] = size
                page_query["page[number]"] = page
            payload = await self._get(path, page_query)
            batch = parser.collection_items(payload)
            page_total = parser.total_records(payload)
            if page_total is not None:
                total = page_total
            page_last = parser.last_page_number(payload)
            if page_last is not None:
                last_page = page_last
            added = 0
            for row in batch:
                key = (str(row.get("type") or ""), str(row.get("id") or ""))
                if key in seen:
                    continue
                seen.add(key)
                items.append(row)
                added += 1
            parser.merge_included(idx, parser.included_index(payload))
            if on_page is not None:
                on_page(len(items), total)
            if size is None:
                if total is not None and len(items) < total:
                    # Vendor documents pagination as disabled here, yet meta reports more
                    # rows: page explicitly instead of keeping a truncated dictionary.
                    logger.warning(
                        "DIDWW %s returned %s of %s rows unpaginated; switching to paging",
                        name,
                        len(items),
                        total,
                    )
                    size = contract.MAX_PAGE_SIZE
                    items.clear()
                    seen.clear()
                    idx.clear()
                    total = None
                    last_page = None
                    page = 1
                    continue
                break
            if total is not None:
                if len(items) >= total:
                    break
                if not batch:
                    break
                if last_page is not None and page >= last_page:
                    break
            else:
                if not batch or not added:
                    break
                if len(batch) < size:
                    break
            page += 1
            if page > contract.MAX_PAGE_NUMBER:
                raise ProviderError(
                    f"DIDWW pagination exceeded safety cap for {name}",
                    code="DIDWW_PAGINATION_CAP",
                    details={"path": path, "fetched": len(items), "total_records": total},
                )
        if total is not None and len(items) < total:
            raise ProviderError(
                f"DIDWW slice incomplete {name}: fetched={len(items)} total_records={total}",
                code="DIDWW_SLICE_INCOMPLETE",
                details={
                    "path": path,
                    "fetched": len(items),
                    "total_records": total,
                    "pages": page,
                    "page_size": size,
                },
            )
        return items, idx

    async def list_countries(self) -> list[dict[str, Any]]:
        # Get Countries: pagination is disabled, the whole list comes in one response.
        items, _idx = await self.iter_collection(
            contract.PATH_COUNTRIES,
            params={"sort": contract.SORT_BY_NAME},
            paginated=False,
            label="countries",
        )
        return items

    async def list_regions(self) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        # Get Regions: pagination is disabled.
        return await self.iter_collection(
            contract.PATH_REGIONS,
            params={"include": contract.REGIONS_INCLUDE, "sort": contract.SORT_BY_NAME},
            paginated=False,
            label="regions",
        )

    async def list_cities(
        self,
        *,
        on_page: PageProgress | None = None,
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        return await self.iter_collection(
            contract.PATH_CITIES,
            params={"include": contract.CITIES_INCLUDE, "sort": contract.SORT_BY_NAME},
            page_size=contract.CITIES_PAGE_SIZE,
            label="cities",
            on_page=on_page,
        )

    async def list_did_group_types(self) -> list[dict[str, Any]]:
        items, _idx = await self.iter_collection(
            contract.PATH_DID_GROUP_TYPES,
            params={"sort": contract.SORT_BY_NAME},
            page_size=contract.TYPES_PAGE_SIZE,
            label="did_group_types",
        )
        return items

    async def list_did_groups(
        self,
        *,
        on_page: PageProgress | None = None,
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        return await self.iter_collection(
            contract.PATH_DID_GROUPS,
            params={
                "include": contract.DID_GROUPS_INCLUDE,
                contract.FILTER_IN_STOCK: "true",
                "sort": contract.SORT_DID_GROUPS,
            },
            page_size=contract.DID_GROUPS_PAGE_SIZE,
            label="did_groups",
            on_page=on_page,
        )

    async def list_available_dids(
        self,
        *,
        did_group_id: str | None = None,
        number_contains: str | None = None,
    ) -> dict[str, Any]:
        """Live read-only lookup. Pagination and sorting are disabled for this endpoint."""
        if not did_group_id and not number_contains:
            raise ProviderError(
                "DIDWW available_dids requires did_group_id or number_contains",
                code="DIDWW_AVAILABLE_DIDS_FILTER_REQUIRED",
            )
        params: dict[str, Any] = {"include": contract.AVAILABLE_DIDS_INCLUDE}
        if did_group_id:
            params[contract.FILTER_AVAILABLE_DID_GROUP] = did_group_id
        if number_contains:
            params[contract.FILTER_AVAILABLE_NUMBER] = number_contains
        return await self._get(contract.PATH_AVAILABLE_DIDS, params)
