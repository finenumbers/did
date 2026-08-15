"""Postgres session-level advisory locks for single-flight sync / cache refresh."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Stable int keys (arbitrary, unique within this DB)
SYNC_LOCK_KEY = 88221001
CACHE_REFRESH_LOCK_KEY = 88221002

SessionT = TypeVar("SessionT", bound=Session)

SYNC_LOCK_BUSY_MSG = "Синхронизация уже выполняется (lock)"
SYNC_LOCK_STUCK_MSG = (
    "Синхронизация заблокирована устаревшим lock — перезапустите backend"
)
SYNC_LOCK_STUCK_CODE = "SYNC_LOCK_STUCK"


def try_advisory_lock(db: Session, key: int) -> bool:
    return bool(db.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}))


def advisory_unlock(db: Session, key: int) -> None:
    """Release session lock. On failure, detach the connection so it never re-enters the pool locked."""
    try:
        unlocked = db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        db.commit()
        if unlocked is False:
            raise RuntimeError(f"pg_advisory_unlock returned false for key={key}")
    except Exception:
        logger.exception("advisory_unlock failed for key=%s; detaching connection", key)
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.connection().detach()
        except Exception:
            logger.exception("Failed to detach connection after unlock failure")
        raise


def detach_session_connection(db: Session) -> None:
    """Drop the DBAPI connection so it cannot re-enter the pool while locked."""
    try:
        db.rollback()
    except Exception:
        pass
    try:
        db.connection().detach()
    except Exception:
        logger.exception("Failed to detach session connection")


def clear_advisory_locks_dbapi(dbapi_conn) -> None:
    """Best-effort unlock of all session advisory locks on a raw DBAPI connection."""
    try:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SELECT pg_advisory_unlock_all()")
        finally:
            cursor.close()
    except Exception:
        # Non-Postgres (sqlite tests) or closed connection — ignore.
        pass


def acquire_sync_lock(
    lock_db: SessionT,
    *,
    other_active_run: Callable[[], bool],
    new_lock_session: Callable[[], SessionT],
    dispose_pool: Callable[[], None],
) -> tuple[bool, SessionT, str | None, bool]:
    """Try SYNC_LOCK_KEY; if held with no other active run, dispose pool and retry once.

    Returns (acquired, lock_db, error_message, pool_disposed).
    On heal, lock_db is a new session and pool_disposed is True (caller must recreate
    any other sessions that were open across dispose).
    error_message is SYNC_LOCK_BUSY_MSG or SYNC_LOCK_STUCK_MSG when not acquired.
    """
    if try_advisory_lock(lock_db, SYNC_LOCK_KEY):
        return True, lock_db, None, False

    if other_active_run():
        return False, lock_db, SYNC_LOCK_BUSY_MSG, False

    logger.warning(
        "Sync lock held with no other active run; disposing engine pool to clear leaked locks"
    )
    try:
        lock_db.close()
    except Exception:
        logger.exception("Failed to close lock session before pool dispose")

    dispose_pool()
    lock_db = new_lock_session()

    if try_advisory_lock(lock_db, SYNC_LOCK_KEY):
        logger.info("Sync lock acquired after pool dispose heal")
        return True, lock_db, None, True

    logger.error("Sync lock still held after pool dispose heal")
    return False, lock_db, SYNC_LOCK_STUCK_MSG, True
