"""Postgres session-level advisory locks for single-flight sync / cache refresh."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Stable int keys (arbitrary, unique within this DB)
SYNC_LOCK_KEY = 88221001
CACHE_REFRESH_LOCK_KEY = 88221002


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
