"""Runexis Numbering pagination recovery (no live API)."""

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

    def __init__(self, scripts: dict[int, list[list[dict]]], *, expected: int):
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
        self._expected = expected
        self.fetch_log: list[tuple[int, int]] = []

    async def search_numbers_count(self, filters: dict) -> int:  # type: ignore[override]
        return self._expected

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
        # Default: synthesize a full page from a contiguous catalog when not scripted
        if chunk is None:
            chunk = []
        return offset, chunk, _raw(), 1


def test_page_all_resumes_sequentially_when_parallel_stops_short():
    """
    Parallel wave ends early (short page + empties) while count is higher.
    Client must discard the short tail and re-fetch from that offset sequentially.
    """
    data = [{"n": i} for i in range(100)]
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        40: [data[40:60]],
        # First visit (parallel): false end; second visit (sequential): full page
        60: [data[60:65], data[60:80]],
        80: [[], data[80:100]],
        100: [[]],
    }
    client = ScriptedNumberingClient(scripts, expected=100)
    items, _envs, expected = asyncio.run(
        client._page_all({}, limit=20, concurrency=4, expected=100)
    )
    assert expected == 100
    assert len(items) == 100
    assert [row["n"] for row in items] == list(range(100))
    # Sequential resume must re-hit offset 60
    assert client.fetch_log.count((60, 20)) >= 2


def test_fetch_remaining_walks_past_short_pages():
    data = [{"n": i} for i in range(50)]
    scripts = {
        30: [data[30:35], data[35:40]],  # first short then continue from 35
        35: [data[35:40]],
        40: [data[40:45]],
        45: [data[45:50]],
        50: [[]],
    }
    # Simpler: remaining scan uses off += len(chunk)
    scripts = {
        30: [data[30:35]],  # short
        35: [data[35:40]],
        40: [data[40:45]],
        45: [data[45:50]],
        50: [[]],
    }
    client = ScriptedNumberingClient(scripts, expected=50)
    extra, _ = asyncio.run(
        client._fetch_remaining({}, start_offset=30, expected=50, limit=5)
    )
    assert len(extra) == 20
    assert [row["n"] for row in extra] == list(range(30, 50))
