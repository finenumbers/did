"""Runexis HTTP client. Doc: Runexis.html Authenticating requests + Auth login/refresh."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig
from app.providers.runexis import contract, parser


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
        auth = connection.auth_settings or {}
        self.email = auth.get("email")
        self.password = auth.get("password")
        self.token = auth.get("token") or auth.get("access_token")
        self.refresh_token = auth.get("refresh_token")
        if not self.token and not (self.email and self.password):
            raise ProviderAuthError(
                "Runexis requires auth_settings.email and auth_settings.password "
                "(VERIFIED: POST api/v1/login). Optional stored Bearer token is also accepted."
            )

    def _auth_headers(self) -> dict[str, str]:
        # VERIFIED: Authorization: Bearer {token}
        if not self.token:
            raise ProviderAuthError("Runexis Bearer token is not available")
        return {
            contract.AUTH_HEADER: f"{contract.AUTH_SCHEME} {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _public_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _apply_tokens(self, tokens: dict[str, str]) -> None:
        self.token = tokens["token"]
        if "refresh_token" in tokens:
            self.refresh_token = tokens["refresh_token"]
        auth = dict(self.connection.auth_settings or {})
        auth["token"] = tokens["token"]
        if "refresh_token" in tokens:
            auth["refresh_token"] = tokens["refresh_token"]
        if "token_expire" in tokens:
            auth["token_expire"] = tokens["token_expire"]
        if "refresh_token_expire" in tokens:
            auth["refresh_token_expire"] = tokens["refresh_token_expire"]
        self.connection.auth_settings = auth

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
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
                        method, url, headers=headers, params=params, json=json_body
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

    async def login(self) -> dict[str, str]:
        # VERIFIED: POST api/v1/login body email + password
        if not self.email or not self.password:
            raise ProviderAuthError("Runexis login requires email and password")
        raw = await self._raw_request(
            "POST",
            contract.POST_LOGIN,
            headers=self._public_headers(),
            json_body={"email": self.email, "password": self.password},
        )
        tokens = parser.parse_auth_tokens(raw)
        self._apply_tokens(tokens)
        return tokens

    async def refresh(self) -> dict[str, str]:
        # VERIFIED: POST api/v1/refresh; body field "token" holds refresh_token value
        if not self.refresh_token:
            raise ProviderAuthError("Runexis refresh_token is not available")
        raw = await self._raw_request(
            "POST",
            contract.POST_REFRESH,
            headers=self._public_headers(),
            json_body={"token": self.refresh_token},
        )
        tokens = parser.parse_auth_tokens(raw)
        self._apply_tokens(tokens)
        return tokens

    async def ensure_token(self) -> None:
        if self.token:
            return
        await self.login()

    async def _recover_auth(self) -> bool:
        """Try refresh, then login. Returns True if a new token was obtained."""
        if self.refresh_token:
            try:
                await self.refresh()
                return True
            except (ProviderAuthError, ProviderTransportError):
                pass
        if self.email and self.password:
            await self.login()
            return True
        return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> RawHttpResult:
        await self.ensure_token()
        raw = await self._raw_request(
            method,
            path,
            headers=self._auth_headers(),
            params=params,
            json_body=json_body,
        )
        if raw.status_code != 401:
            return raw
        recovered = await self._recover_auth()
        if not recovered:
            return raw
        return await self._raw_request(
            method,
            path,
            headers=self._auth_headers(),
            params=params,
            json_body=json_body,
        )

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
        # VERIFIED: GET api/v1/numbers/management — partner inventory list
        return await self._request("GET", contract.GET_NUMBERS_MANAGEMENT, params=params)

    async def list_all_numbers_management(
        self, *, extra_params: dict[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate management list using EXAMPLE-CONFIRMED meta.total/page/limit."""
        page = 1
        limit = contract.MANAGEMENT_PAGE_LIMIT
        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        while True:
            params: dict[str, Any] = {"page": page, "limit": limit}
            if extra_params:
                params.update(extra_params)
            raw = await self.get_numbers_management(params)
            envelopes.append(raw)
            if raw.status_code >= 400:
                break
            body = raw.body_json if isinstance(raw.body_json, dict) else {}
            chunk = body.get("data") or []
            if not isinstance(chunk, list):
                break
            items.extend([x for x in chunk if isinstance(x, dict)])
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            total = meta.get("total")
            if not chunk:
                break
            if total is not None and len(items) >= int(total):
                break
            page += 1
            if page > 10_000:
                break
        return items, envelopes
