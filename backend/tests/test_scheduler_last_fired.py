"""Scheduler must not burn the day when cache is not ready."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.modules.sync_engine import scheduler


def test_tick_does_not_set_last_fired_when_cache_not_ready():
    db = MagicMock()
    fake_now = datetime(2026, 8, 3, 21, 0, tzinfo=ZoneInfo("Europe/Moscow"))

    with (
        patch.object(scheduler, "SessionLocal", return_value=db),
        patch.object(
            scheduler,
            "get_sync_schedule",
            return_value={"enabled": True, "hour": 21, "minute": 0},
        ),
        patch.object(scheduler, "get_active_run", return_value=None),
        patch.object(scheduler, "is_min_cache_ready", return_value=False),
        patch.object(scheduler, "_get_last_fired_date", return_value=None),
        patch.object(scheduler, "_set_last_fired_date") as set_fired,
        patch.object(scheduler, "datetime") as dt,
    ):
        dt.now.return_value = fake_now
        scheduler._tick_once()
        set_fired.assert_not_called()


def test_tick_sets_last_fired_after_successful_create():
    db = MagicMock()
    fake_now = datetime(2026, 8, 3, 21, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    run = SimpleNamespace(id="run-1")

    with (
        patch.object(scheduler, "SessionLocal", return_value=db),
        patch.object(
            scheduler,
            "get_sync_schedule",
            return_value={"enabled": True, "hour": 21, "minute": 0},
        ),
        patch.object(scheduler, "get_active_run", return_value=None),
        patch.object(scheduler, "is_min_cache_ready", return_value=True),
        patch.object(scheduler, "_get_last_fired_date", return_value=None),
        patch.object(scheduler, "create_run", return_value=run),
        patch.object(scheduler, "spawn_unified_run") as spawn,
        patch.object(scheduler, "_set_last_fired_date") as set_fired,
        patch.object(scheduler, "datetime") as dt,
    ):
        dt.now.return_value = fake_now
        scheduler._tick_once()
        spawn.assert_called_once_with("run-1")
        set_fired.assert_called_once_with(db, "2026-08-03")
