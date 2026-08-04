"""Aurora Telecom CSV client — read-only GET of free numbers export."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.providers.aurora import contract
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)

PROBE_MAX_BYTES = 65_536
_ALLOWED_HOST = "bill.auroratelecom.ru"


class AuroraClient:
    def __init__(
        self,
        connection: ConnectionConfig,
        *,
        timeout: TimeoutConfig | None = None,
        retry: RetryPolicy | None = None,
    ):
        self.connection = connection
        self.timeout = timeout or TimeoutConfig(
            connect_timeout=15.0,
            read_timeout=180.0,
            total_timeout=200.0,
        )
        self.retry = retry or RetryPolicy()
        self.csv_url = (connection.base_url or "").strip() or contract.DEFAULT_CSV_URL
        self._validate_url(self.csv_url)

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ProviderTransportError(f"Aurora URL scheme not allowed: {parsed.scheme!r}")
        host = (parsed.hostname or "").lower()
        if host != _ALLOWED_HOST:
            raise ProviderTransportError(
                f"Aurora URL host not allowed: {host!r} (expected {_ALLOWED_HOST})"
            )

    def _client_kwargs(self, timeout: httpx.Timeout) -> dict[str, Any]:
        return {
            "timeout": timeout,
            "follow_redirects": False,
            "trust_env": False,
        }

    async def fetch_csv(self) -> RawHttpResult:
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(**self._client_kwargs(timeout)) as client:
                return await client.get(self.csv_url)

        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label="Aurora CSV fetch",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"Aurora CSV HTTP {response.status_code}",
                details={"status_code": response.status_code},
            )
        content = response.content
        if len(content) > contract.MAX_CSV_BYTES:
            raise ProviderTransportError(
                f"Aurora CSV exceeded MAX_CSV_BYTES={contract.MAX_CSV_BYTES}"
            )
        return RawHttpResult(
            status_code=response.status_code,
            body_text=content.decode("latin-1"),
            body_json={"bytes_len": len(content), "encoding_hint": "binary_via_latin1"},
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url),
        )

    async def fetch_csv_head(self, *, max_bytes: int = PROBE_MAX_BYTES) -> RawHttpResult:
        """Stream only the first bytes for connection test (not full sync)."""
        timeout = httpx.Timeout(
            min(self.timeout.total_timeout, 60.0),
            connect=self.timeout.connect_timeout,
            read=min(self.timeout.read_timeout, 60.0),
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(**self._client_kwargs(timeout)) as client:
                async with client.stream("GET", self.csv_url) as response:
                    # For retryable statuses, drain and return as-is
                    if response.status_code in self.retry.retry_on_status:
                        await response.aread()
                        return httpx.Response(
                            status_code=response.status_code,
                            headers=response.headers,
                            content=b"",
                            request=response.request,
                        )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        if not chunk:
                            continue
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= max_bytes:
                            break
                    content = b"".join(chunks)[:max_bytes]
                    headers = dict(response.headers)
                    headers["x-did-truncated"] = "1" if total >= max_bytes else "0"
                    return httpx.Response(
                        status_code=response.status_code,
                        headers=headers,
                        content=content,
                        request=response.request,
                    )

        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label="Aurora CSV head",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        content = response.content
        truncated = response.headers.get("x-did-truncated") == "1"
        return RawHttpResult(
            status_code=response.status_code,
            body_text=content.decode("latin-1"),
            body_json={
                "bytes_len": len(content),
                "encoding_hint": "binary_via_latin1",
                "truncated": truncated,
            },
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url) if response.url else self.csv_url,
        )

    def raw_bytes(self, raw: RawHttpResult) -> bytes:
        """Recover original bytes stored via latin-1 body_text."""
        return raw.body_text.encode("latin-1")

    async def probe(self) -> tuple[RawHttpResult, dict[str, Any]]:
        """Fetch CSV head for test_connection (bounded)."""
        raw = await self.fetch_csv_head()
        return raw, {
            "url": self.csv_url,
            "bytes": len(self.raw_bytes(raw)),
            "status_code": raw.status_code,
            "truncated": bool((raw.body_json or {}).get("truncated")),
        }
