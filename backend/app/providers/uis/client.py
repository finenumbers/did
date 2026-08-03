"""UIS Data API JSON-RPC client. Docs: uis-contract.md — read-only get.* + login.user."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderAuthError, ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig
from app.providers.uis import contract


class UisClient:
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
        self.base_url = (connection.base_url or contract.EXAMPLE_BASE_URL).rstrip("/")
        self.page_limit = min(page_limit or contract.DEFAULT_LIMIT, contract.MAX_LIMIT)
        auth = connection.auth_settings or {}
        self._token = (auth.get(contract.AUTH_ACCESS_TOKEN) or "").strip() or None
        self._login = (auth.get(contract.AUTH_LOGIN) or "").strip() or None
        self._password = auth.get(contract.AUTH_PASSWORD) or None
        user_id = auth.get(contract.AUTH_USER_ID)
        self._user_id: int | None = None
        if user_id is not None and str(user_id).strip() != "":
            try:
                self._user_id = int(user_id)
            except (TypeError, ValueError) as exc:
                raise ProviderAuthError(
                    f"UIS auth_settings.user_id must be a number, got {user_id!r}"
                ) from exc

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
        last_exc: Exception | None = None
        for attempt in range(self.retry.max_attempts):
            try:
                start = time.perf_counter()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self.base_url,
                        json=envelope,
                        headers={"Content-Type": "application/json; charset=UTF-8"},
                    )
                elapsed = (time.perf_counter() - start) * 1000
                body_json: Any | None
                try:
                    body_json = response.json()
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
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt + 1 >= self.retry.max_attempts:
                    break
        raise ProviderTransportError(f"UIS transport failed: {last_exc}")

    async def login_user(self) -> RawHttpResult:
        if not self._login or not self._password:
            raise ProviderAuthError(
                "UIS requires access_token or login+password "
                "(VERIFIED: login.user / permanent key)"
            )
        return await self.call(
            contract.METHOD_LOGIN_USER,
            {"login": self._login, "password": self._password},
        )

    async def resolve_access_token(self) -> str:
        """Prefer stored token; otherwise login.user and persist into auth_settings."""
        if self._token:
            return self._token
        raw = await self.login_user()
        from app.providers.uis.parser import parse_login

        token, expire_at = parse_login(raw)
        self._token = token
        self.connection.auth_settings[contract.AUTH_ACCESS_TOKEN] = token
        if expire_at is not None:
            self.connection.auth_settings[contract.AUTH_SESSION_EXPIRE_AT] = expire_at
        return token

    def _auth_params(self, token: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {contract.AUTH_ACCESS_TOKEN: token}
        if self._user_id is not None:
            params[contract.AUTH_USER_ID] = self._user_id
        if extra:
            params.update(extra)
        return params

    async def get_page(
        self,
        method: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> RawHttpResult:
        token = await self.resolve_access_token()
        return await self.call(
            method,
            self._auth_params(
                token,
                {
                    "offset": offset,
                    "limit": limit if limit is not None else self.page_limit,
                },
            ),
        )

    async def iter_all(
        self,
        method: str,
        *,
        on_progress: Any | None = None,
    ) -> tuple[list[dict[str, Any]], list[RawHttpResult]]:
        """Paginate until offset >= total_items or short page."""
        from app.providers.uis.parser import parse_list_page

        items: list[dict[str, Any]] = []
        envelopes: list[RawHttpResult] = []
        offset = 0
        total: int | None = None
        while offset <= contract.MAX_OFFSET:
            raw = await self.get_page(method, offset=offset, limit=self.page_limit)
            envelopes.append(raw)
            page_items, page_total = parse_list_page(raw)
            if total is None and page_total is not None:
                total = page_total
            items.extend(page_items)
            if on_progress:
                try:
                    on_progress(
                        f"UIS {method} offset={offset}",
                        len(items),
                        total,
                    )
                except Exception:
                    logger.exception("UIS on_progress failed")
            if not page_items:
                break
            offset += len(page_items)
            if total is not None and offset >= total:
                break
            if len(page_items) < self.page_limit:
                break
        return items, envelopes
