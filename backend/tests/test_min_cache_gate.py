"""Min PSTN INN cache gate (mocked session)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.pstn_inn_cache.service import (
    REQUIRED_INNS,
    is_min_cache_ready,
    is_operator_ready,
    require_min_cache_ready,
)
from app.providers.errors import ProviderError


def test_is_operator_ready_requires_ranges_and_enabled():
    op = SimpleNamespace(enabled=True, ranges_count=0, last_error=None)
    assert is_operator_ready(op) is False
    op.ranges_count = 10
    assert is_operator_ready(op) is True
    op.enabled = False
    assert is_operator_ready(op) is False


def test_is_min_cache_ready_all_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.ensure_required_operators",
        lambda db: None,
    )
    ready_ops = [
        SimpleNamespace(inn=inn, enabled=True, ranges_count=5, last_error=None)
        for inn in REQUIRED_INNS
    ]
    db = MagicMock()
    db.scalars.return_value.all.return_value = ready_ops
    assert is_min_cache_ready(db) is True

    ready_ops[0].ranges_count = 0
    assert is_min_cache_ready(db) is False


def test_require_min_cache_ready_raises_when_not_ready(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.is_refresh_running",
        lambda db: False,
    )
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.is_min_cache_ready",
        lambda db: False,
    )
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.missing_required_inns",
        lambda db: ["ООО «СИПАУТНЭТ» (5920032027)"],
    )
    with pytest.raises(ProviderError) as exc:
        require_min_cache_ready(MagicMock())
    assert exc.value.code == "PSTN_INN_CACHE_NOT_READY"


def test_require_min_cache_ready_blocks_during_refresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.is_refresh_running",
        lambda db: True,
    )
    with pytest.raises(ProviderError) as exc:
        require_min_cache_ready(MagicMock())
    assert exc.value.code == "PSTN_INN_CACHE_REFRESH_RUNNING"


def test_require_min_cache_ready_ok(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.is_refresh_running",
        lambda db: False,
    )
    monkeypatch.setattr(
        "app.modules.pstn_inn_cache.service.is_min_cache_ready",
        lambda db: True,
    )
    require_min_cache_ready(MagicMock())
