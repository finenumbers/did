from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.sync_engine.unified import _run_mask_types


def test_mask_types_stage_rolls_back_before_error_log(monkeypatch):
    db = MagicMock()
    order: list[str] = []
    db.rollback.side_effect = lambda: order.append("rollback")

    def log(*_args, **_kwargs):
        order.append("log")

    monkeypatch.setattr("app.modules.sync_engine.unified.log_run", log)
    monkeypatch.setattr(
        "app.services.mask_types_service.ensure_mask_types_seeded",
        lambda _db: 0,
    )
    monkeypatch.setattr(
        "app.modules.catalog.apply_mask_types.apply_mask_types",
        lambda _db: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    tracker = MagicMock()
    _run_mask_types(
        db,
        run=SimpleNamespace(id=uuid4()),
        tracker=tracker,
        category_stats={},
    )
    assert order[0] == "rollback"
    assert "log" in order
    tracker.fail.assert_called_once()
    db.commit.assert_not_called()
