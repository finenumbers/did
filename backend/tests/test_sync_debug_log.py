"""Tests for overwriteable sync debug log file."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.modules.sync_engine.run_file_log import (
    begin_sync_debug_log,
    end_sync_debug_log,
    get_sync_debug_log,
    mirror_db_log,
    sync_debug_log_exists,
    sync_debug_log_path,
)


def _patch_log_path(monkeypatch, path: Path) -> None:
    monkeypatch.setenv("SYNC_DEBUG_LOG_PATH", str(path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.modules.sync_engine.run_file_log.get_settings",
        lambda: type("S", (), {"sync_debug_log_path": str(path)})(),
    )


def test_truncate_on_new_sync(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    run1 = uuid.uuid4()
    begin_sync_debug_log(run1, triggered_by="api")
    fl = get_sync_debug_log()
    assert fl is not None
    fl.stage_begin("prepare", "first")
    fl.write("INFO", "KEEP_ME_UNTIL_TRUNCATE")
    # Flush visible before close
    text1 = path.read_text(encoding="utf-8")
    assert str(run1) in text1
    assert "=== BEGIN prepare ===" in text1
    assert "KEEP_ME_UNTIL_TRUNCATE" in text1
    end_sync_debug_log(status="success")

    run2 = uuid.uuid4()
    begin_sync_debug_log(run2, triggered_by="schedule")
    text2 = path.read_text(encoding="utf-8")
    assert str(run2) in text2
    assert "KEEP_ME_UNTIL_TRUNCATE" not in text2
    assert str(run1) not in text2
    end_sync_debug_log(status="failed", error_summary="boom")
    final = path.read_text(encoding="utf-8")
    assert "status=failed" in final
    assert "error=boom" in final


def test_partial_flush_before_close(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    run_id = uuid.uuid4()
    begin_sync_debug_log(run_id)
    fl = get_sync_debug_log()
    assert fl is not None
    fl.stage_begin("runexis_free")
    fl.stage_progress(
        "runexis_free",
        detail="Numbering: страница 1",
        current=20000,
        total=432669,
        unit="numbers",
    )
    mirror_db_log("info", "job started", source="job")
    # File must already contain progress without close()
    body = path.read_text(encoding="utf-8")
    assert "=== BEGIN runexis_free ===" in body
    assert "current=20000" in body
    assert "[job] job started" in body
    assert sync_debug_log_exists()
    assert sync_debug_log_path() == path
    end_sync_debug_log()


def test_provider_logger_mirrored(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    begin_sync_debug_log(uuid.uuid4())
    try:
        logging.getLogger("app.providers.runexis.numbering_client").warning(
            "Runexis Numbering search_numbers page=2 offset=20000 got=20000 ms=41200"
        )
        body = path.read_text(encoding="utf-8")
        assert "page=2 offset=20000" in body
        assert "[py:app.providers.runexis.numbering_client]" in body
    finally:
        end_sync_debug_log()
