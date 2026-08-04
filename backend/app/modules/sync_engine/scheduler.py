"""Daily unified sync at/after 00:00 Europe/Moscow — only if min INN cache is ready."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
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
    row = db.scalar(
        select(SystemSetting).where(SystemSetting.key == LAST_FIRED_SETTING_KEY)
    )
    if not row or not isinstance(row.value, dict):
        return None
    day = row.value.get("date")
    return str(day) if day else None


def _set_last_fired_date(db, day_key: str) -> None:
    row = db.scalar(
        select(SystemSetting).where(SystemSetting.key == LAST_FIRED_SETTING_KEY)
    )
    if row is None:
        row = SystemSetting(
            key=LAST_FIRED_SETTING_KEY,
            value={"date": day_key},
            description="Last scheduled sync lock-claim (MSK calendar day; not necessarily success)",
            is_secret=False,
        )
        db.add(row)
    else:
        row.value = {"date": day_key}
        flag_modified(row, "value")
    db.commit()


def _tick_once() -> None:
    db = SessionLocal()
    try:
        schedule = get_sync_schedule(db)
        if not schedule.get("enabled"):
            return
        hour = int(schedule.get("hour", 0))
        minute = int(schedule.get("minute", 0))
        now = datetime.now(_MSK)
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Same-day window: any poll at/after scheduled time until midnight next day
        if now < scheduled:
            return
        day_key = now.date().isoformat()
        if _get_last_fired_date(db) == day_key:
            return
        if get_active_run(db) is not None:
            # Do not burn the day — retry next poll while still same calendar day
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
        # last_fired is set in execute_unified_run after advisory lock is acquired
        spawn_unified_run(run.id)
        logger.warning("Scheduled sync spawned run_id=%s", run.id)
    finally:
        db.close()


async def sync_schedule_loop(*, poll_seconds: float = 30.0) -> None:
    while True:
        try:
            _tick_once()
        except Exception:
            logger.exception("sync schedule tick failed")
        await asyncio.sleep(poll_seconds)
