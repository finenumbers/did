"""Aurora Telecom CSV client — read-only GET of configured free exports."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.providers.aurora import contract
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderTransportError
from app.providers.retry import RetryPolicy, TimeoutConfig, request_with_retries

logger = logging.getLogger(__name__)

PROBE_MAX_BYTES = 65_536


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
        self.csv_files = contract.load_csv_files(connection.extra_settings)
        self.csv_urls = [e.url for e in self.csv_files]
        # First URL used for probe / back-compat attribute
        self.csv_url = self.csv_urls[0]
        self.first_entry = self.csv_files[0]

    @staticmethod
    def _validate_url(url: str) -> None:
        contract.validate_csv_url(url)

    def _client_kwargs(self, timeout: httpx.Timeout) -> dict[str, Any]:
        return {
            "timeout": timeout,
            "follow_redirects": False,
            "trust_env": False,
        }

    async def fetch_csv(self, url: str | None = None) -> RawHttpResult:
        target = url or self.csv_url
        self._validate_url(target)
        timeout = httpx.Timeout(
            self.timeout.total_timeout,
            connect=self.timeout.connect_timeout,
            read=self.timeout.read_timeout,
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(**self._client_kwargs(timeout)) as client:
                return await client.get(target)

        fname = contract.csv_filename(target)
        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label=f"Aurora CSV fetch {fname}",
            do_request=_once,
        )
        elapsed = (time.perf_counter() - start) * 1000
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"Aurora CSV HTTP {response.status_code} for {fname}",
                details={"status_code": response.status_code, "file": fname, "url": target},
            )
        content = response.content
        if len(content) > contract.MAX_CSV_BYTES:
            raise ProviderTransportError(
                f"Aurora CSV {fname} exceeded MAX_CSV_BYTES={contract.MAX_CSV_BYTES}",
                details={"file": fname, "bytes": len(content)},
            )
        return RawHttpResult(
            status_code=response.status_code,
            body_text=content.decode("latin-1"),
            body_json={"bytes_len": len(content), "encoding_hint": "binary_via_latin1"},
            headers=dict(response.headers),
            elapsed_ms=elapsed,
            request_url=str(response.url),
        )

    async def fetch_csv_head(
        self, url: str | None = None, *, max_bytes: int = PROBE_MAX_BYTES
    ) -> RawHttpResult:
        """Stream only the first bytes for connection test (not full sync)."""
        target = url or self.csv_url
        self._validate_url(target)
        timeout = httpx.Timeout(
            min(self.timeout.total_timeout, 60.0),
            connect=self.timeout.connect_timeout,
            read=min(self.timeout.read_timeout, 60.0),
        )

        async def _once() -> httpx.Response:
            async with httpx.AsyncClient(**self._client_kwargs(timeout)) as client:
                async with client.stream("GET", target) as response:
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

        fname = contract.csv_filename(target)
        start = time.perf_counter()
        response = await request_with_retries(
            retry=self.retry,
            label=f"Aurora CSV head {fname}",
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
            request_url=str(response.url) if response.url else target,
        )

    def raw_bytes(self, raw: RawHttpResult) -> bytes:
        """Recover original bytes stored via latin-1 body_text."""
        return raw.body_text.encode("latin-1")

    async def probe(self) -> tuple[RawHttpResult, dict[str, Any]]:
        """Fetch CSV head of the first configured file for test_connection."""
        entry = self.first_entry
        raw = await self.fetch_csv_head(entry.url)
        return raw, {
            "url": entry.url,
            "has_status_column": entry.has_status_column,
            "files": [contract.csv_filename(e.url) for e in self.csv_files],
            "bytes": len(self.raw_bytes(raw)),
            "status_code": raw.status_code,
            "truncated": bool((raw.body_json or {}).get("truncated")),
        }
