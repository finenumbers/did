"""Runexis Numbering pagination (no live API)."""

from __future__ import annotations

import asyncio
import time

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

    def __init__(
        self,
        scripts: dict[int, list[list[dict]]],
        *,
        count_hint: int,
        delays: dict[int, float] | None = None,
    ):
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
        self._delays = delays or {}
        self._delay_used: set[int] = set()
        self.fetch_log: list[tuple[int, int]] = []
        self.cancelled_high_offsets: list[int] = []

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
        delay = float(self._delays.get(offset, 0))
        if delay and offset not in self._delay_used:
            self._delay_used.add(offset)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                self.cancelled_high_offsets.append(offset)
                raise
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
    items, _envs, meta = asyncio.run(
        client._page_all({}, limit=20, concurrency=4, count_hint=500)
    )
    assert meta["count_hint"] == 500
    assert meta["sequential_verify"] is True
    assert meta["final_short_page_offset"] == 100
    assert meta["count_hint_gap"] == 400
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
    items, _envs, meta = asyncio.run(
        client._page_all({}, limit=20, concurrency=1, count_hint=200)
    )
    assert meta["count_hint"] == 200
    assert meta["count_hint_gap"] == 155
    assert meta["sequential_verify"] is False
    assert meta["final_short_page_offset"] == 40
    assert len(items) == 45


def test_list_all_free_documents_count_hint_progress_only_policy():
    """list_all_free_numbers must expose progress-only gap policy, not fail."""
    from app.providers.runexis import contract as runexis_contract

    data = [{"n": i, "access_state": 0} for i in range(45)]
    limit = 20
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        40: [data[40:45]],
        60: [[]],
    }
    client = ScriptedNumberingClient(scripts, count_hint=200)

    async def _noop() -> None:
        return None

    client.connect = _noop  # type: ignore[method-assign]
    client.aclose = _noop  # type: ignore[method-assign]

    # Pin page size so scripted offsets match contract concurrency path.
    orig_limit = runexis_contract.NUMBERING_PAGE_LIMIT
    orig_conc = runexis_contract.NUMBERING_FETCH_CONCURRENCY
    runexis_contract.NUMBERING_PAGE_LIMIT = limit
    runexis_contract.NUMBERING_FETCH_CONCURRENCY = 1
    try:
        items, _envs, meta = asyncio.run(client.list_all_free_numbers())
    finally:
        runexis_contract.NUMBERING_PAGE_LIMIT = orig_limit
        runexis_contract.NUMBERING_FETCH_CONCURRENCY = orig_conc

    assert len(items) == 45
    assert meta["count_hint_policy"] == "progress_only"
    assert meta["count_hint_semantics"] == "api_search_total_not_free_list_size"
    assert meta["count_hint_gap"] == 155
    assert meta["list_ended_naturally"] is True


def test_page_all_soft_verifies_large_short_without_refetch():
    """Large short page + empty next offset → accept without re-fetching short."""
    data = [{"n": i} for i in range(52)]
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        # 12/20 >= soft_verify_min (limit//2) → peek offset 60, do not re-fetch 40
        40: [data[40:52]],
        60: [[]],
        80: [[]],
        100: [[]],
    }
    client = ScriptedNumberingClient(scripts, count_hint=500)
    items, _envs, meta = asyncio.run(
        client._page_all({}, limit=20, concurrency=4, count_hint=500)
    )
    assert len(items) == 52
    assert meta["soft_verify"] is True
    assert meta["sequential_verify"] is True
    assert meta["final_short_page_offset"] == 40
    assert client.fetch_log.count((40, 20)) == 1
    assert client.fetch_log.count((60, 20)) >= 1


def test_page_all_restores_concurrency_after_hard_verify_false_short():
    """Tiny false-short hard-verifies, then restores parallel for the remainder."""
    data = [{"n": i} for i in range(100)]
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        40: [data[40:60]],
        # tiny short (5 < limit//2) → hard verify; second response full
        60: [data[60:65], data[60:80]],
        80: [[], data[80:100]],
        100: [[]],
        120: [[]],
        140: [[]],
    }
    client = ScriptedNumberingClient(scripts, count_hint=500)
    items, _envs, meta = asyncio.run(
        client._page_all({}, limit=20, concurrency=4, count_hint=500)
    )
    assert len(items) == 100
    assert [row["n"] for row in items] == list(range(100))
    assert meta["sequential_verify"] is True
    assert meta.get("soft_verify") is False
    assert client.fetch_log.count((60, 20)) >= 2


def test_page_all_cancels_higher_offsets_after_short_page():
    """Short page must cancel slower higher-offset siblings (wall-time win)."""
    data = [{"n": i} for i in range(45)]
    scripts = {
        0: [data[0:20]],
        20: [data[20:40]],
        # parallel short + sequential-verify short (script queue)
        40: [data[40:45], data[40:45]],
        60: [[]],
        80: [[]],
        100: [[]],
    }
    client = ScriptedNumberingClient(
        scripts,
        count_hint=500,
        delays={60: 2.0, 80: 2.0, 100: 2.0},
    )
    t0 = time.perf_counter()
    items, _envs, meta = asyncio.run(
        client._page_all({}, limit=20, concurrency=4, count_hint=500)
    )
    elapsed = time.perf_counter() - t0
    assert len(items) == 45
    assert meta["sequential_verify"] is True
    assert elapsed < 1.5  # would be ~2s+ without cancel
    assert client.cancelled_high_offsets  # at least one higher offset cancelled


def test_page_all_emits_pending_progress_before_slow_calls():
    """UI should not stay blank while count / page1 RPC are in flight."""
    events: list[tuple[str, int | None, int | None]] = []

    def on_progress(detail: str, current=None, total=None):
        events.append((detail, current, total))

    scripts = {0: [[{"n": 1}] * 5]}
    client = ScriptedNumberingClient(scripts, count_hint=42)
    items, _envs, meta = asyncio.run(
        client._page_all({}, limit=20, concurrency=1, on_progress=on_progress)
    )
    assert meta["count_hint"] == 42
    assert meta["count_hint_gap"] == 37
    assert meta["sequential_verify"] is False
    assert meta["final_short_page_offset"] == 0
    assert len(items) == 5
    details = [e[0] for e in events]
    assert "Numbering: запрос count" in details
    assert "Numbering: загрузка страницы 1" in details
    # Pending page1 shows 0 / total before the first page returns
    pending = next(e for e in events if e[0] == "Numbering: загрузка страницы 1")
    assert pending[1] == 0 and pending[2] == 42
    assert any(d.startswith("Numbering: страница 1") for d in details)


def test_list_all_free_emits_session_progress():
    events: list[str] = []

    def on_progress(detail: str, current=None, total=None):
        events.append(detail)

    scripts = {0: [[{"n": 1}, {"n": 2}]]}
    client = ScriptedNumberingClient(scripts, count_hint=2)

    async def fake_connect():
        return "session"

    async def fake_aclose():
        return None

    client.connect = fake_connect  # type: ignore[method-assign]
    client.aclose = fake_aclose  # type: ignore[method-assign]

    items, _envs, meta = asyncio.run(client.list_all_free_numbers(on_progress=on_progress))
    assert len(items) == 2
    assert events[0] == "Numbering: подключение"
    assert "Numbering: сессия" in events
    assert "Numbering: запрос count" in events
    assert "Numbering: загрузка страницы 1" in events
