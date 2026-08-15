"""Postgres session-level advisory locks for single-flight sync / cache refresh.

Long-held locks (sync, PSTN cache refresh) MUST use Connections from ``lock_engine``
(NullPool). Never hold them via Session on the main engine: Session.commit() returns
the connection to the pool, and main-pool checkin runs pg_advisory_unlock_all().
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Stable int keys (arbitrary, unique within this DB)
SYNC_LOCK_KEY = 88221001
CACHE_REFRESH_LOCK_KEY = 88221002

SYNC_LOCK_BUSY_MSG = "Синхронизация уже выполняется (lock)"
SYNC_LOCK_STUCK_MSG = (
    "Синхронизация заблокирована устаревшим lock — перезапустите backend"
)
SYNC_LOCK_STUCK_CODE = "SYNC_LOCK_STUCK"


def try_advisory_lock(db: Session, key: int) -> bool:
    """Short-lived try on a Session (reclaim/stale). Do not hold across Session.commit()."""
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


def try_advisory_lock_conn(conn: Connection, key: int) -> bool:
    """Acquire advisory lock on a held Connection; commit ends the txn but keeps the checkout."""
    acquired = bool(
        conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()
    )
    conn.commit()
    return acquired


def advisory_unlock_conn(conn: Connection, key: int) -> None:
    """Release advisory lock on a held Connection. On failure, invalidate the connection."""
    try:
        unlocked = conn.execute(
            text("SELECT pg_advisory_unlock(:k)"), {"k": key}
        ).scalar()
        conn.commit()
        if unlocked is False:
            raise RuntimeError(f"pg_advisory_unlock returned false for key={key}")
    except Exception:
        logger.exception("advisory_unlock_conn failed for key=%s; invalidating", key)
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.invalidate()
        except Exception:
            logger.exception("Failed to invalidate connection after unlock failure")
        raise


def ping_lock_conn(conn: Connection) -> None:
    """Keepalive on the same held Connection (does not return it to any pool)."""
    conn.execute(text("SELECT 1"))
    conn.commit()


def clear_advisory_locks_dbapi(dbapi_conn) -> None:
    """Best-effort unlock of all session advisory locks on a raw DBAPI connection.

    Must leave the connection idle (not INTRANS): pool_pre_ping sets autocommit and
    fails if a prior checkin SELECT left an open transaction.
    """
    try:
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("SELECT pg_advisory_unlock_all()")
        finally:
            cursor.close()
        dbapi_conn.commit()
    except Exception:
        try:
            dbapi_conn.rollback()
        except Exception:
            pass
        # Non-Postgres (sqlite tests) or closed connection — ignore.


def acquire_sync_lock(
    *,
    other_active_run: Callable[[], bool],
    dispose_main_pool: Callable[[], None],
    connect: Callable[[], Connection] | None = None,
) -> tuple[bool, Connection | None, str | None, bool]:
    """Try SYNC_LOCK_KEY on lock_engine; if held with no other active run, dispose main pool once.

    Returns (acquired, lock_conn, error_message, main_pool_disposed).
    Caller must keep lock_conn open until unlock+close. Never Session.commit the lock.
    """
    from app.core.db import lock_engine

    open_conn = connect or lock_engine.connect
    conn = open_conn()
    try:
        if try_advisory_lock_conn(conn, SYNC_LOCK_KEY):
            return True, conn, None, False

        if other_active_run():
            conn.close()
            return False, None, SYNC_LOCK_BUSY_MSG, False

        logger.warning(
            "Sync lock held with no other active run; disposing main engine pool to clear leaked locks"
        )
        try:
            conn.close()
        except Exception:
            logger.exception("Failed to close probe lock connection before main pool dispose")

        dispose_main_pool()
        conn = open_conn()
        if try_advisory_lock_conn(conn, SYNC_LOCK_KEY):
            logger.info("Sync lock acquired after main pool dispose heal")
            return True, conn, None, True

        logger.error("Sync lock still held after main pool dispose heal")
        try:
            conn.close()
        except Exception:
            logger.exception("Failed to close lock connection after stuck acquire")
        return False, None, SYNC_LOCK_STUCK_MSG, True
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


def acquire_cache_refresh_lock(
    *,
    connect: Callable[[], Connection] | None = None,
) -> tuple[bool, Connection | None]:
    """Try CACHE_REFRESH_LOCK_KEY on lock_engine. Caller holds conn until unlock+close."""
    from app.core.db import lock_engine

    open_conn = connect or lock_engine.connect
    conn = open_conn()
    try:
        if try_advisory_lock_conn(conn, CACHE_REFRESH_LOCK_KEY):
            return True, conn
        conn.close()
        return False, None
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise
