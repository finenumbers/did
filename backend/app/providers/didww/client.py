"""DIDWW JSON:API GET-only client. Never POST/PATCH/DELETE."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.didww import contract, parser
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)


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

        response = await request_with_retries(
            retry=self.retry,
            label=f"DIDWW GET {path}",
            do_request=_do,
        )
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
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        query = dict(params or {})
        items: list[dict[str, Any]] = []
        idx: dict[tuple[str, str], dict[str, Any]] = {}
        page = 1
        while True:
            page_query = dict(query)
            if paginated and page_size:
                page_query["page[size]"] = page_size
                page_query["page[number]"] = page
            payload = await self._get(path, page_query)
            batch = parser.collection_items(payload)
            items.extend(batch)
            parser.merge_included(idx, parser.included_index(payload))
            links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
            next_link = links.get("next") if paginated else None
            if not next_link or not batch:
                break
            page += 1
            if page > 20000:
                raise ProviderError("DIDWW pagination exceeded safety cap")
        return items, idx

    async def list_countries(self) -> list[dict[str, Any]]:
        items, _idx = await self.iter_collection(contract.PATH_COUNTRIES, paginated=False)
        return items

    async def list_regions(self) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        return await self.iter_collection(
            contract.PATH_REGIONS,
            params={"include": contract.REGIONS_INCLUDE},
            page_size=contract.REGIONS_PAGE_SIZE,
        )

    async def list_cities(self) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        return await self.iter_collection(
            contract.PATH_CITIES,
            params={"include": contract.CITIES_INCLUDE},
            page_size=contract.CITIES_PAGE_SIZE,
        )

    async def list_did_group_types(self) -> list[dict[str, Any]]:
        items, _idx = await self.iter_collection(
            contract.PATH_DID_GROUP_TYPES,
            page_size=contract.TYPES_PAGE_SIZE,
        )
        return items

    async def list_did_groups(self) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        return await self.iter_collection(
            contract.PATH_DID_GROUPS,
            params={
                "include": contract.DID_GROUPS_INCLUDE,
                contract.FILTER_IN_STOCK: "true",
            },
            page_size=contract.DID_GROUPS_PAGE_SIZE,
        )

    async def get_balance(self) -> dict[str, Any]:
        return await self._get(contract.PATH_BALANCE)

    async def list_available_dids(
        self,
        *,
        did_group_id: str | None = None,
        number_contains: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"include": contract.AVAILABLE_DIDS_INCLUDE}
        if did_group_id:
            params["filter[did_group.id]"] = did_group_id
        if number_contains:
            params["filter[number_contains]"] = number_contains
        return await self._get(contract.PATH_AVAILABLE_DIDS, params)
