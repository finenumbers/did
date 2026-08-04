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
