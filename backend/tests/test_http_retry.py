"""Provider HTTP retry honors retry_on_status + backoff."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.providers.errors import ProviderTransportError
from app.providers.retry import RetryPolicy, request_with_retries


def test_request_with_retries_retries_503_then_succeeds():
    calls = {"n": 0}

    async def _once() -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, request=httpx.Request("GET", "http://x"))
        return httpx.Response(200, content=b"ok", request=httpx.Request("GET", "http://x"))

    with patch("app.providers.retry.asyncio.sleep", new_callable=AsyncMock) as sleep:
        resp = asyncio.run(
            request_with_retries(
                retry=RetryPolicy(max_attempts=3, backoff_seconds=0.01),
                label="test",
                do_request=_once,
            )
        )
    assert resp.status_code == 200
    assert calls["n"] == 3
    assert sleep.await_count == 2


def test_request_with_retries_raises_after_transport_exhaustion():
    async def _once() -> httpx.Response:
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "http://x"))

    with (
        patch("app.providers.retry.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(ProviderTransportError, match="transport failed"),
    ):
        asyncio.run(
            request_with_retries(
                retry=RetryPolicy(max_attempts=2, backoff_seconds=0.01),
                label="test",
                do_request=_once,
            )
        )
