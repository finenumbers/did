"""Shared emit_progress awaits async callbacks."""

from __future__ import annotations

import asyncio

from app.providers.progress_emit import emit_progress


def test_emit_progress_awaits_async_callback():
    seen: list[tuple] = []

    async def cb(detail: str, current=None, total=None):
        await asyncio.sleep(0)
        seen.append((detail, current, total))

    asyncio.run(emit_progress(cb, "UIS: get…", 1, 10))
    assert seen == [("UIS: get…", 1, 10)]


def test_emit_progress_sync_callback():
    seen: list[str] = []

    def cb(detail: str, current=None, total=None):
        seen.append(detail)

    asyncio.run(emit_progress(cb, "SipOut: free_list…"))
    assert seen == ["SipOut: free_list…"]


def test_emit_progress_none_is_noop():
    asyncio.run(emit_progress(None, "x"))
