"""Postgres session-level advisory locks for single-flight sync / cache refresh."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers.errors import ProviderError

# Stable int keys (arbitrary, unique within this DB)
SYNC_LOCK_KEY = 88221001
CACHE_REFRESH_LOCK_KEY = 88221002


def try_advisory_lock(db: Session, key: int) -> bool:
    return bool(db.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}))


def advisory_unlock(db: Session, key: int) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
    db.commit()


@contextmanager
def hold_advisory_lock(
    db: Session,
    key: int,
    *,
    busy_code: str,
    busy_message: str,
) -> Iterator[None]:
    if not try_advisory_lock(db, key):
        raise ProviderError(busy_message, code=busy_code)
    db.commit()
    try:
        yield
    finally:
        try:
            advisory_unlock(db, key)
        except Exception:
            pass
