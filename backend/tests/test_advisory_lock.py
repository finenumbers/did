"""Advisory unlock / lock_engine Connection hold contracts."""

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
    dbapi.commit.assert_called_once()
    dbapi.rollback.assert_not_called()


def test_clear_advisory_locks_dbapi_swallows_errors():
    dbapi = MagicMock()
    dbapi.cursor.side_effect = RuntimeError("not postgres")

    locks.clear_advisory_locks_dbapi(dbapi)  # must not raise
    dbapi.rollback.assert_called_once()


def test_clear_advisory_locks_dbapi_rollback_when_commit_fails():
    dbapi = MagicMock()
    cursor = MagicMock()
    dbapi.cursor.return_value = cursor
    dbapi.commit.side_effect = RuntimeError("commit failed")

    locks.clear_advisory_locks_dbapi(dbapi)
    dbapi.rollback.assert_called_once()


def test_try_advisory_lock_conn_commits_but_caller_keeps_connection():
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = True

    assert locks.try_advisory_lock_conn(conn, locks.SYNC_LOCK_KEY) is True
    conn.commit.assert_called_once()
    conn.close.assert_not_called()


def test_advisory_unlock_conn_invalidates_on_failure():
    conn = MagicMock()
    conn.execute.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        locks.advisory_unlock_conn(conn, locks.SYNC_LOCK_KEY)

    conn.invalidate.assert_called_once()


def test_acquire_sync_lock_succeeds_first_try():
    conn = MagicMock()
    dispose = MagicMock()
    connect = MagicMock(return_value=conn)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock_conn", lambda _c, _k: True)
        ok, held, err, disposed = locks.acquire_sync_lock(
            other_active_run=lambda: True,
            dispose_main_pool=dispose,
            connect=connect,
        )

    assert ok is True
    assert held is conn
    assert err is None
    assert disposed is False
    dispose.assert_not_called()
    connect.assert_called_once()
    conn.close.assert_not_called()


def test_acquire_sync_lock_busy_when_other_active():
    conn = MagicMock()
    dispose = MagicMock()
    connect = MagicMock(return_value=conn)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock_conn", lambda _c, _k: False)
        ok, held, err, disposed = locks.acquire_sync_lock(
            other_active_run=lambda: True,
            dispose_main_pool=dispose,
            connect=connect,
        )

    assert ok is False
    assert held is None
    assert err == locks.SYNC_LOCK_BUSY_MSG
    assert disposed is False
    dispose.assert_not_called()
    conn.close.assert_called_once()


def test_acquire_sync_lock_heals_via_dispose_when_no_other_active():
    probe = MagicMock()
    healed = MagicMock()
    dispose = MagicMock()
    connect = MagicMock(side_effect=[probe, healed])
    tries = {"n": 0}

    def try_lock(_c, _k):
        tries["n"] += 1
        return tries["n"] >= 2

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock_conn", try_lock)
        ok, held, err, disposed = locks.acquire_sync_lock(
            other_active_run=lambda: False,
            dispose_main_pool=dispose,
            connect=connect,
        )

    assert ok is True
    assert held is healed
    assert err is None
    assert disposed is True
    probe.close.assert_called_once()
    dispose.assert_called_once()
    assert connect.call_count == 2
    assert tries["n"] == 2
    healed.close.assert_not_called()


def test_acquire_sync_lock_stuck_after_failed_heal():
    probe = MagicMock()
    healed = MagicMock()
    dispose = MagicMock()
    connect = MagicMock(side_effect=[probe, healed])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock_conn", lambda _c, _k: False)
        ok, held, err, disposed = locks.acquire_sync_lock(
            other_active_run=lambda: False,
            dispose_main_pool=dispose,
            connect=connect,
        )

    assert ok is False
    assert held is None
    assert err == locks.SYNC_LOCK_STUCK_MSG
    assert disposed is True
    dispose.assert_called_once()
    probe.close.assert_called_once()
    healed.close.assert_called_once()


def test_acquire_cache_refresh_lock_holds_connection():
    conn = MagicMock()
    connect = MagicMock(return_value=conn)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(locks, "try_advisory_lock_conn", lambda _c, _k: True)
        ok, held = locks.acquire_cache_refresh_lock(connect=connect)

    assert ok is True
    assert held is conn
    conn.close.assert_not_called()
