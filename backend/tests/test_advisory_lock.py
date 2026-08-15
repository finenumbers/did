"""Advisory unlock must not return a locked connection to the pool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.sync_engine import locks


def test_advisory_unlock_detaches_on_failure():
    db = MagicMock()
    db.scalar.side_effect = RuntimeError("db down")
    conn = MagicMock()
    db.connection.return_value = conn

    with pytest.raises(RuntimeError, match="db down"):
        locks.advisory_unlock(db, locks.SYNC_LOCK_KEY)

    conn.detach.assert_called_once()


def test_advisory_unlock_detaches_when_unlock_returns_false():
    db = MagicMock()
    db.scalar.return_value = False
    conn = MagicMock()
    db.connection.return_value = conn

    with pytest.raises(RuntimeError, match="returned false"):
        locks.advisory_unlock(db, locks.SYNC_LOCK_KEY)

    conn.detach.assert_called_once()


def test_clear_advisory_locks_dbapi_runs_unlock_all():
    dbapi = MagicMock()
    cursor = MagicMock()
    dbapi.cursor.return_value = cursor

    locks.clear_advisory_locks_dbapi(dbapi)

    cursor.execute.assert_called_once_with("SELECT pg_advisory_unlock_all()")
    cursor.close.assert_called_once()


def test_clear_advisory_locks_dbapi_swallows_errors():
    dbapi = MagicMock()
    dbapi.cursor.side_effect = RuntimeError("not postgres")

    locks.clear_advisory_locks_dbapi(dbapi)  # must not raise


def test_acquire_sync_lock_succeeds_first_try():
    lock_db = MagicMock()
    dispose = MagicMock()
    new_session = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock", lambda _db, _k: True)
        ok, session, err, disposed = locks.acquire_sync_lock(
            lock_db,
            other_active_run=lambda: True,
            new_lock_session=new_session,
            dispose_pool=dispose,
        )

    assert ok is True
    assert session is lock_db
    assert err is None
    assert disposed is False
    dispose.assert_not_called()
    new_session.assert_not_called()


def test_acquire_sync_lock_busy_when_other_active():
    lock_db = MagicMock()
    dispose = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock", lambda _db, _k: False)
        ok, session, err, disposed = locks.acquire_sync_lock(
            lock_db,
            other_active_run=lambda: True,
            new_lock_session=MagicMock(),
            dispose_pool=dispose,
        )

    assert ok is False
    assert session is lock_db
    assert err == locks.SYNC_LOCK_BUSY_MSG
    assert disposed is False
    dispose.assert_not_called()


def test_acquire_sync_lock_heals_via_dispose_when_no_other_active():
    lock_db = MagicMock()
    healed_db = MagicMock()
    dispose = MagicMock()
    new_session = MagicMock(return_value=healed_db)
    tries = {"n": 0}

    def try_lock(_db, _k):
        tries["n"] += 1
        return tries["n"] >= 2

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock", try_lock)
        ok, session, err, disposed = locks.acquire_sync_lock(
            lock_db,
            other_active_run=lambda: False,
            new_lock_session=new_session,
            dispose_pool=dispose,
        )

    assert ok is True
    assert session is healed_db
    assert err is None
    assert disposed is True
    lock_db.close.assert_called_once()
    dispose.assert_called_once()
    new_session.assert_called_once()
    assert tries["n"] == 2


def test_acquire_sync_lock_stuck_after_failed_heal():
    lock_db = MagicMock()
    healed_db = MagicMock()
    dispose = MagicMock()
    new_session = MagicMock(return_value=healed_db)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock", lambda _db, _k: False)
        ok, session, err, disposed = locks.acquire_sync_lock(
            lock_db,
            other_active_run=lambda: False,
            new_lock_session=new_session,
            dispose_pool=dispose,
        )

    assert ok is False
    assert session is healed_db
    assert err == locks.SYNC_LOCK_STUCK_MSG
    assert disposed is True
    dispose.assert_called_once()
