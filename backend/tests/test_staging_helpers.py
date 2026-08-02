"""Lock key sanity."""

from app.modules.sync_engine.locks import CACHE_REFRESH_LOCK_KEY, SYNC_LOCK_KEY


def test_lock_keys_distinct():
    assert SYNC_LOCK_KEY != CACHE_REFRESH_LOCK_KEY
    assert isinstance(SYNC_LOCK_KEY, int)
