"""SipOut HTTP client — method/action query style. Doc: SipOut.html Основные положения."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries
from app.providers.sipout import contract


class SipOutClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig()
        self.retry = retry or RetryPolicy()
        self.base_url = (connection.base_url or contract.EXAMPLE_BASE_URL).rstrip("/") + "/"
        self.api_key = connection.auth_settings.get("key") or connection.auth_settings.get("api_key")
        if not self.api_key:
            raise ProviderAuthError("SipOut auth_settings.key is required (VERIFIED: query key)")

    async def call(
        self,
        method: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> RawHttpResult:
        # VERIFIED: https://lk.sipout.net/userapi/?key=&method=&action=[&params]
        query: dict[str, Any] = {
            contract.AUTH_QUERY_PARAM: self.api_key,
            "method": method,
            "action": action,
        }
        if params:
            # Only pass explicitly provided documented params
            query.update({k: v for k, v in params.items() if v is not None})

        url = urljoin(self.base_url, "")
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                return await client.get(url, params=query)

        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label=f"SipOut {method}.{action}",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        body_json: Any | None
        try:
            body_json = response.json()
        except Exception:
            body_json = None
        return RawHttpResult(
            status_code=response.status_code,
            body_text=response.text,
            body_json=body_json,
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url),
        )

    async def get_balance(self) -> RawHttpResult:
        # VERIFIED: method=balance&action=get
        return await self.call(contract.METHOD_BALANCE, contract.ACTION_BALANCE_GET)

    async def get_cities(self) -> RawHttpResult:
        # VERIFIED: method=did&action=get_cities
        return await self.call(contract.METHOD_DID, contract.ACTION_GET_CITIES)

    async def free_list(
        self, *, city_id: str | None = None, mask: str | None = None
    ) -> RawHttpResult:
        # VERIFIED: method=did&action=free_list; optional city_id, mask
        params: dict[str, Any] = {}
        if city_id is not None:
            params[contract.FREE_LIST_PARAM_CITY_ID] = city_id
        if mask is not None:
            params[contract.FREE_LIST_PARAM_MASK] = mask
        return await self.call(contract.METHOD_DID, contract.ACTION_FREE_LIST, params or None)

    async def connected_list(self) -> RawHttpResult:
        # VERIFIED: method=did&action=connected_list
        return await self.call(contract.METHOD_DID, contract.ACTION_CONNECTED_LIST)
