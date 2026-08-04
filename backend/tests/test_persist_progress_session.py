"""UI progress / job log must use a separate Session so persist Session stays clean."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.modules.sync_engine import service as sync_service


def test_throttled_progress_uses_separate_session_and_rollback_on_error():
    persist_db = MagicMock()
    job_id = uuid4()
    run_id = uuid4()
    persist_db.get.return_value = SimpleNamespace(
        stats={"sync_run_id": str(run_id)},
    )

    side_db = MagicMock()
    tracker = MagicMock()
    tracker.progress.side_effect = RuntimeError("commit failed")

    with (
        patch.object(sync_service, "SessionLocal", return_value=side_db) as session_factory,
        patch.object(sync_service, "SyncProgressTracker", return_value=tracker),
        patch.object(
            sync_service,
            "stage_for_provider_phase",
            return_value="aurora_free",
        ),
        patch.object(sync_service, "log_job") as log_job,
        patch.object(sync_service.time, "monotonic", return_value=10.0),
    ):
        cb = sync_service._throttled_persist_progress(
            persist_db,
            job_id=job_id,
            provider_code="aurora",
            phase="free",
        )
        cb("staging", 1, 10)

        log_job.assert_called_once_with(
            side_db, job_id, sync_service.SyncLogLevel.info, "staging (1/10)"
        )
        session_factory.assert_called_once()
        side_db.rollback.assert_called_once()
        side_db.close.assert_called_once()
        # Persist session must not be rolled back by side-session failure
        persist_db.rollback.assert_not_called()
