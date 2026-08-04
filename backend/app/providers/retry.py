"""System-level timeout/retry — OPERATIONAL, not derived from provider docs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from app.providers.errors import ProviderTransportError

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    total_timeout: float = 90.0


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 1.0
    retry_on_status: list[int] = field(default_factory=lambda: [502, 503, 504])


async def request_with_retries(
    *,
    retry: RetryPolicy,
    label: str,
    do_request: Callable[[], Awaitable[httpx.Response]],
) -> httpx.Response:
    """Execute HTTP request with backoff on transport errors and retry_on_status."""
    last_exc: Exception | None = None
    last_response: httpx.Response | None = None
    for attempt in range(retry.max_attempts):
        try:
            response = await do_request()
            last_response = response
            if response.status_code in retry.retry_on_status:
                if attempt + 1 >= retry.max_attempts:
                    return response
                delay = retry.backoff_seconds * (attempt + 1)
                logger.warning(
                    "%s attempt %s got HTTP %s; retrying in %.1fs",
                    label,
                    attempt + 1,
                    response.status_code,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt + 1 >= retry.max_attempts:
                break
            delay = retry.backoff_seconds * (attempt + 1)
            logger.warning(
                "%s attempt %s transport error: %s; retrying in %.1fs",
                label,
                attempt + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    if last_response is not None:
        return last_response
    raise ProviderTransportError(f"{label} transport failed: {last_exc}")
