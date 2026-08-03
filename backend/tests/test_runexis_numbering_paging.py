"""Runexis Numbering pagination (no live API)."""

from __future__ import annotations

import asyncio

from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.runexis.numbering_client import RunexisNumberingClient


def _raw() -> RawHttpResult:
    return RawHttpResult(
        status_code=200,
        body_text="{}",
        body_json={"result": []},
        headers={},
        elapsed_ms=1.0,
        request_url="https://example.test/",
    )


class ScriptedNumberingClient(RunexisNumberingClient):
    """Serves scripted pages: offset -> queue of chunk responses."""

    def __init__(self, scripts: dict[int, list[list[dict]]], *, count_hint: int):
        super().__init__(
            ConnectionConfig(
                base_url="https://example.test",
                auth_settings={
                    "numbering_login": "u",
                    "numbering_password": "p",
                },
            )
        )
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self._count_hint = count_hint
        self.fetch_log: list[tuple[int, int]] = []

    async def search_numbers_count(self, filters: dict) -> int:  # type: ignore[override]
        return self._count_hint

    async def _fetch_page(  # type: ignore[override]
        self,
        filters: dict,
        *,
        offset: int,
        limit: int,
    ) -> tuple[int, list, RawHttpResult, int]:
        self.fetch_log.append((offset, limit))
        queue = self._scripts.setdefault(offset, [[]])
        chunk = queue.pop(0) if queue else []
        return offset, chunk, _raw(), 1


def test_page_all_resumes_sequentially_when_parallel_stops_early():
    """
    Parallel wave ends early (short page + empties). Client verifies once
    sequentially from that offset — even when count_hint is much larger.
    """
    data = [{"n": i} for i in range(100)]
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        40: [data[40:60]],
        60: [data[60:65], data[60:80]],
        80: [[], data[80:100]],
        100: [[]],
    }
    client = ScriptedNumberingClient(scripts, count_hint=500)
    items, _envs, hint = asyncio.run(
        client._page_all({}, limit=20, concurrency=4, count_hint=500)
    )
    assert hint == 500
    assert len(items) == 100
    assert [row["n"] for row in items] == list(range(100))
    assert client.fetch_log.count((60, 20)) >= 2


def test_page_all_accepts_free_list_below_count_hint():
    """Natural end of free list must succeed when count_hint is API total."""
    data = [{"n": i} for i in range(45)]
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        40: [data[40:45]],
        60: [[]],
    }
    client = ScriptedNumberingClient(scripts, count_hint=200)
    items, _envs, hint = asyncio.run(
        client._page_all({}, limit=20, concurrency=1, count_hint=200)
    )
    assert hint == 200
    assert len(items) == 45
