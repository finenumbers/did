"""Daily unified sync at 21:00 Europe/Moscow — only if min INN cache is ready."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal
from app.models.providers import SystemSetting
from app.modules.pstn_inn_cache.service import get_sync_schedule, is_min_cache_ready
from app.modules.sync_engine.unified import create_run, get_active_run, spawn_unified_run
from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)

_MSK = ZoneInfo("Europe/Moscow")
LAST_FIRED_SETTING_KEY = "sync_schedule_last_fired"


def _get_last_fired_date(db) -> str | None:
    from sqlalchemy import select

    row = db.scalar(select(SystemSetting).where(SystemSetting.key == LAST_FIRED_SETTING_KEY))
    if row is None:
        return None
    value = row.value or {}
    return value.get("date")


def _set_last_fired_date(db, day_key: str) -> None:
    from sqlalchemy import select

    row = db.scalar(select(SystemSetting).where(SystemSetting.key == LAST_FIRED_SETTING_KEY))
    if row is None:
        row = SystemSetting(
            key=LAST_FIRED_SETTING_KEY,
            value={"date": day_key},
            description="Last successful scheduled sync fire (MSK calendar day)",
            is_secret=False,
        )
        db.add(row)
    else:
        row.value = {"date": day_key}
        flag_modified(row, "value")
    db.commit()


async def sync_schedule_loop(*, poll_seconds: float = 30.0) -> None:
    """Background loop: fire once per calendar day at configured MSK time."""
    while True:
        try:
            _tick_once()
        except Exception:
            logger.exception("Sync schedule tick failed")
        await asyncio.sleep(poll_seconds)


def _tick_once() -> None:
    db = SessionLocal()
    try:
        schedule = get_sync_schedule(db)
        if not schedule.get("enabled"):
            return
        hour = int(schedule.get("hour", 21))
        minute = int(schedule.get("minute", 0))
        now = datetime.now(_MSK)
        if now.hour != hour or now.minute != minute:
            return
        day_key = now.date().isoformat()
        if _get_last_fired_date(db) == day_key:
            return
        if get_active_run(db) is not None:
            # Do not burn the day — retry next poll while still in the minute window
            logger.warning("Scheduled sync deferred: already running")
            return
        if not is_min_cache_ready(db):
            # Do not burn the day — retry after cache is loaded (same day)
            logger.warning(
                "Scheduled sync deferred: PSTN INN min cache not ready (load cache in Settings)"
            )
            return
        try:
            run = create_run(db, triggered_by="schedule")
        except ProviderError as exc:
            logger.warning("Scheduled sync not started: %s", exc.message)
            return
        spawn_unified_run(run.id)
        _set_last_fired_date(db, day_key)
        logger.warning("Scheduled sync started run_id=%s", run.id)
    finally:
        db.close()
