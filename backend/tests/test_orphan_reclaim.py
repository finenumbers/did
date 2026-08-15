"""Abort progress finalization + orphan reclaim updates stages."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models.enums import SyncJobStatus
from app.modules.sync_engine import unified
from app.modules.sync_engine.progress import (
    apply_progress_abort,
    build_initial_progress,
    finalize_progress_on_abort,
    stage_status,
)


def test_finalize_progress_on_abort_closes_open_stages():
    progress = build_initial_progress()
    for stage in progress["stages"]:
        if stage["id"] == "prepare":
            stage["status"] = "done"
            stage["detail"] = "ok"
        elif stage["id"] == "sipout_free":
            stage["status"] = "running"
            stage["detail"] = "staging 10/10"
        # else pending

    out = finalize_progress_on_abort(progress, "Marked orphan: running but sync lock was free")
    assert out is not None
    assert stage_status(out, "prepare") == "done"
    assert stage_status(out, "sipout_free") == "failed"
    sipout = next(s for s in out["stages"] if s["id"] == "sipout_free")
    assert "aborted:" in sipout["detail"]
    assert "staging 10/10" in sipout["detail"]
    assert stage_status(out, "sipout_purchased") == "skipped"
    assert out["current_stage_id"] is None


def test_reclaim_orphaned_running_when_lock_free():
    db = MagicMock()
    progress = build_initial_progress()
    progress["stages"][1]["status"] = "running"
    progress["stages"][1]["detail"] = "in flight"
    run = SimpleNamespace(
        id=uuid4(),
        status=SyncJobStatus.running,
        error_summary=None,
        finished_at=None,
        progress=progress,
    )
    db.scalars.return_value.all.return_value = [run]

    with (
        patch("app.modules.sync_engine.locks.try_advisory_lock", return_value=True),
        patch("app.modules.sync_engine.locks.advisory_unlock") as unlock,
        patch.object(unified, "log_run"),
    ):
        n = unified.reclaim_orphaned_running_runs(db)

    assert n == 1
    assert run.status == SyncJobStatus.failed
    assert "orphan" in (run.error_summary or "").lower()
    assert stage_status(run.progress, progress["stages"][1]["id"]) == "failed"
    unlock.assert_called_once()
    db.commit.assert_called_once()


def test_reclaim_skips_when_lock_held():
    db = MagicMock()
    run = SimpleNamespace(id=uuid4(), status=SyncJobStatus.running, progress=None)
    db.scalars.return_value.all.return_value = [run]

    with patch("app.modules.sync_engine.locks.try_advisory_lock", return_value=False):
        n = unified.reclaim_orphaned_running_runs(db)

    assert n == 0
    assert run.status == SyncJobStatus.running
    db.commit.assert_not_called()


def test_apply_progress_abort_noop_without_progress():
    run = SimpleNamespace(progress=None)
    apply_progress_abort(run, "Interrupted by server restart")
    assert run.progress is None


def test_progress_tracker_raises_when_run_failed():
    from app.modules.sync_engine.progress import SyncAborted, SyncProgressTracker

    progress = build_initial_progress()
    for stage in progress["stages"]:
        if stage["id"] == "sipout_free":
            stage["status"] = "failed"
            stage["detail"] = "aborted: orphan"

    run = SimpleNamespace(
        id=uuid4(),
        status=SyncJobStatus.failed,
        progress=progress,
    )
    db = MagicMock()
    db.get.return_value = run

    tracker = SyncProgressTracker(db, run.id)
    with pytest.raises(SyncAborted):
        tracker.progress("sipout_free", detail="should not stick", current=1, total=10)

    # Status must remain failed — zombie overwrite blocked.
    assert stage_status(run.progress, "sipout_free") == "failed"
