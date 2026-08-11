"""Voximplant Management API HTTP client. Docs: voximplant-contract.md."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderError, ProviderTransportError
from app.providers.progress_emit import emit_progress
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries
from app.providers.voximplant import contract, parser
from app.providers.voximplant.auth_jwt import JwtTokenCache

logger = logging.getLogger(__name__)


class VoximplantClient:
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
        if not raw_base.startswith("http"):
            raw_base = f"https://{raw_base}"
        self.base_url = raw_base.rstrip("/")
        self.page_limit = int(page_limit or contract.DEFAULT_PAGE_LIMIT)
        self._jwt = JwtTokenCache(connection.auth_settings)
        self._api_host_override: str | None = None

    def _platform_url(self, method: str, params: dict[str, Any] | None = None) -> str:
        host = self._api_host_override or self.base_url
        if not host.startswith("http"):
            host = f"https://{host}"
        path = f"{host.rstrip('/')}/platform_api/{method}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        if not clean:
            return path
        return f"{path}?{urlencode(clean, doseq=True)}"

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> RawHttpResult:
        token = self._jwt.get_token()
        url = self._platform_url(method, params)
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                return await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                )

        start = time.perf_counter()
        try:
            response = await request_with_retries(
                retry=self.retry,
                label=f"Voximplant {method}",
                do_request=_once,
            )
        except Exception as exc:
            raise ProviderTransportError(
                f"Voximplant {method} transport failed: {exc}"
            ) from exc
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
                f"Voximplant {method} HTTP {response.status_code}",
                details={"status": response.status_code, "hint": "VOXIMPLANT_AUTH_FAILED"},
            )
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"Voximplant {method} HTTP {response.status_code}",
                details={"status": response.status_code, "body": (response.text or "")[:500]},
            )
        if isinstance(body_json, dict):
            err = body_json.get("error")
            if isinstance(err, dict) and err.get("code") == 314:
                # Let retry policy handle via raising transport-ish error for callers
                raise ProviderTransportError(
                    "Voximplant concurrent resource limit exceeded (314)",
                    details={"api_error": err},
                )
            parser.raise_for_api_error(body_json, context=method)
        return raw

    async def get_account_info(self) -> tuple[dict[str, Any], RawHttpResult]:
        raw = await self.call(contract.METHOD_GET_ACCOUNT_INFO)
        body = parser.require_mapping_body(raw.body_json, method=contract.METHOD_GET_ACCOUNT_INFO)
        api_address = body.get("api_address")
        if isinstance(api_address, str) and api_address.strip():
            self._api_host_override = api_address.strip()
        result = body.get("result")
        return (result if isinstance(result, dict) else {}), raw

    async def get_ru_categories(self) -> tuple[list[dict[str, Any]], RawHttpResult]:
        raw = await self.call(
            contract.METHOD_GET_CATEGORIES,
            {
                "country_code": contract.COUNTRY_CODE_RU,
                "sandbox": contract.SANDBOX_REAL,
                "locale": contract.LOCALE_RU,
            },
        )
        body = parser.require_mapping_body(raw.body_json, method=contract.METHOD_GET_CATEGORIES)
        return parser.extract_ru_categories(body), raw

    async def get_regions(self, category: str) -> tuple[list[dict[str, Any]], RawHttpResult]:
        raw = await self.call(
            contract.METHOD_GET_REGIONS,
            {
                "country_code": contract.COUNTRY_CODE_RU,
                "phone_category_name": category,
                "locale": contract.LOCALE_RU,
                "omit_empty": "true",
            },
        )
        body = parser.require_mapping_body(raw.body_json, method=contract.METHOD_GET_REGIONS)
        return parser.extract_regions(body, category=category), raw

    async def get_new_phones_page(
        self,
        *,
        category: str,
        region_id: int,
        offset: int,
        count: int | None = None,
    ) -> tuple[list[dict[str, Any]], int | None, int, RawHttpResult]:
        raw = await self.call(
            contract.METHOD_GET_NEW_PHONES,
            {
                "country_code": contract.COUNTRY_CODE_RU,
                "phone_category_name": category,
                "phone_region_id": int(region_id),
                "count": int(count if count is not None else self.page_limit),
                "offset": int(offset),
            },
        )
        body = parser.require_mapping_body(raw.body_json, method=contract.METHOD_GET_NEW_PHONES)
        items, total, returned = parser.extract_new_phones_page(body)
        return items, total, returned, raw

    async def iter_free_slice(
        self,
        *,
        category: str,
        region_id: int,
        region_name: str | None = None,
        on_progress: Callable[..., Any] | None = None,
        expected_phone_count: int | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult], dict[str, Any]]:
        """Paginate one category×region until total_count exhausted. Fail on shortfall."""
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        page_limit = self.page_limit
        total_count: int | None = None
        await emit_progress(
            on_progress,
            f"Voximplant free {category} region={region_id}",
        )
        while offset <= contract.MAX_OFFSET:
            page, total, returned, raw = await self.get_new_phones_page(
                category=category,
                region_id=region_id,
                offset=offset,
                count=page_limit,
            )
            envelopes.append(raw)
            if total_count is None and total is not None:
                total_count = total
            if not page:
                break
            for it in page:
                row = dict(it)
                row["_vox_category"] = category
                row["_vox_region_id"] = region_id
                if region_name:
                    row["_vox_region_name"] = region_name
                items.append(row)
            # Prefer API returned count; fall back to len(page)
            step = returned if returned > 0 else len(page)
            offset += step
            if total_count is not None and offset >= total_count:
                break
            if len(page) < page_limit and (
                total_count is None or offset >= total_count
            ):
                break
            if offset > contract.MAX_OFFSET:
                raise ProviderError(
                    (
                        f"Voximplant free pagination truncated category={category} "
                        f"region={region_id} offset={offset}"
                    ),
                    code="VOXIMPLANT_PAGINATION_TRUNCATED",
                    details={
                        "category": category,
                        "region_id": region_id,
                        "offset": offset,
                        "fetched": len(items),
                        "total_count": total_count,
                        "expected_phone_count": expected_phone_count,
                    },
                )

        meta = {
            "category": category,
            "region_id": region_id,
            "fetched": len(items),
            "total_count": total_count,
            "expected_phone_count": expected_phone_count,
        }
        if total_count is not None and len(items) < total_count:
            raise ProviderError(
                (
                    f"Voximplant slice incomplete category={category} "
                    f"region={region_id}: fetched={len(items)} total_count={total_count}"
                ),
                code="VOXIMPLANT_SLICE_INCOMPLETE",
                details=meta,
            )
        return items, envelopes, meta
