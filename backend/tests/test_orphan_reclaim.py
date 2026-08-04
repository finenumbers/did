"""Reclaim SyncRun stuck in running when advisory lock is free."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.enums import SyncJobStatus
from app.modules.sync_engine import unified


def test_reclaim_orphaned_running_when_lock_free():
    db = MagicMock()
    run = SimpleNamespace(
        id=uuid4(),
        status=SyncJobStatus.running,
        error_summary=None,
        finished_at=None,
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
    unlock.assert_called_once()
    db.commit.assert_called_once()


def test_reclaim_skips_when_lock_held():
    db = MagicMock()
    run = SimpleNamespace(id=uuid4(), status=SyncJobStatus.running)
    db.scalars.return_value.all.return_value = [run]

    with patch("app.modules.sync_engine.locks.try_advisory_lock", return_value=False):
        n = unified.reclaim_orphaned_running_runs(db)

    assert n == 0
    assert run.status == SyncJobStatus.running
    db.commit.assert_not_called()
