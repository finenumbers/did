"""Shared sync progress callback helper (await async callbacks safely)."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, int | None, int | None], Any]


async def emit_progress(
    on_progress: ProgressCb | None,
    detail: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if on_progress is None:
        return
    try:
        result = on_progress(detail, current, total)
        if inspect.isawaitable(result):
            await result  # type: ignore[misc]
    except Exception:
        logger.exception("Sync progress callback failed: %s", detail)
