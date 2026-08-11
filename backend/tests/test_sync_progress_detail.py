"""Sync stage detail / progress counter semantics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.modules.sync_engine.progress import SyncProgressTracker, build_initial_progress


def test_stage_end_clears_inflight_progress_counters():
    run_id = uuid4()
    progress = build_initial_progress()
    stage = next(s for s in progress["stages"] if s["id"] == "sipout_free")
    stage["status"] = "running"
    stage["detail"] = "Буфер → каталог"
    stage["substage"] = "Буфер → каталог"
    stage["progress"] = {"current": 100, "total": 1000, "unit": "numbers"}

    run = SimpleNamespace(id=run_id, progress=progress)
    db = MagicMock()
    db.get.return_value = run

    tracker = SyncProgressTracker(db, run_id)
    with patch.object(tracker, "_save", lambda r: None):
        tracker.end(
            "sipout_free",
            "fetched=1000, parsed=1000, upserted=1000, unmapped_dropped=0, duplicates_dropped=0",
        )

    done = next(s for s in run.progress["stages"] if s["id"] == "sipout_free")
    assert done["status"] == "done"
    assert "fetched=1000" in done["detail"]
    assert done["substage"] == ""
    assert done["progress"]["current"] is None
    assert done["progress"]["total"] is None
    assert done["progress"]["unit"] == ""
