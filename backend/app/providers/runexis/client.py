"""Runexis HTTP client. Doc: Runexis.html Authenticating requests + endpoint paths."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig
from app.providers.runexis import contract


class RunexisClient:
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
        self.token = connection.auth_settings.get("token") or connection.auth_settings.get(
            "access_token"
        )
        if not self.token:
            raise ProviderAuthError(
                "Runexis auth_settings.token is required (VERIFIED: Bearer {token})"
            )

    def _headers(self) -> dict[str, str]:
        # VERIFIED: Authorization: Bearer {token}
        return {
            contract.AUTH_HEADER: f"{contract.AUTH_SCHEME} {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> RawHttpResult:
        url = urljoin(self.base_url, path)
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            try:
                start = time.perf_counter()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method, url, headers=self._headers(), params=params, json=json_body
                    )
                elapsed = (time.perf_counter() - start) * 1000
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
                    request_url=str(response.request.url),
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 >= self.retry.max_attempts:
                    break
        raise ProviderTransportError(f"Runexis transport failed: {last_exc}")

    async def get_me(self) -> RawHttpResult:
        # VERIFIED: GET api/v1/me
        return await self._request("GET", contract.GET_ME)

    async def get_regions(self) -> RawHttpResult:
        # VERIFIED: GET api/v1/regions
        return await self._request("GET", contract.GET_REGIONS)

    async def get_cities(self) -> RawHttpResult:
        # VERIFIED: GET api/v1/regions/cities
        return await self._request("GET", contract.GET_CITIES)

    async def get_numbers(self, params: dict[str, Any] | None = None) -> RawHttpResult:
        # VERIFIED: GET api/v1/numbers — NOT wired to free/purchased sync
        return await self._request("GET", contract.GET_NUMBERS, params=params)

    async def get_numbers_management(self, params: dict[str, Any] | None = None) -> RawHttpResult:
        # VERIFIED: GET api/v1/numbers/management — NOT wired to free/purchased sync
        return await self._request("GET", contract.GET_NUMBERS_MANAGEMENT, params=params)
