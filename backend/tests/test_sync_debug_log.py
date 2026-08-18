"""Tests for overwriteable sync debug log file."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.sync_engine.geo_log_dump import (
    dump_sync_geo_diagnostics,
    is_unusual_gar_territory,
)
from app.modules.sync_engine.run_file_log import (
    begin_sync_debug_log,
    end_sync_debug_log,
    get_sync_debug_log,
    mirror_db_log,
    sync_debug_log_exists,
    sync_debug_log_path,
)

LONG_GEO = (
    "Республика Адыгея, Республика Алтай, Республика Башкортостан, "
    "Республика Бурятия, Республика Дагестан, Республика Ингушетия, "
    "Кабардино-Балкарская Республика, Республика Калмыкия, "
    "Карачаево-Черкесская Республика, Республика Карелия, "
    "Республика Коми, Республика Крым, Республика Марий Эл, "
    "Республика Мордовия, Республика Саха (Якутия), "
    "Республика Северная Осетия — Алания, Республика Татарстан"
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


def test_mirror_db_log_writes_full_context(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    begin_sync_debug_log(uuid.uuid4())
    try:
        mirror_db_log(
            "info",
            "enrich_stats",
            source="run",
            context={"city_name": LONG_GEO, "n": 42, "when": object()},
        )
        body = path.read_text(encoding="utf-8")
        assert "[run] enrich_stats context=" in body
        assert LONG_GEO in body
        assert '"n": 42' in body
        assert "..." not in body
    finally:
        end_sync_debug_log()


def test_exception_traceback_in_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    begin_sync_debug_log(uuid.uuid4())
    try:
        try:
            raise RuntimeError("GAR_TRACE_MARKER")
        except RuntimeError:
            logging.getLogger("app.modules.catalog.gar_territory").exception(
                "failed parse"
            )
        body = path.read_text(encoding="utf-8")
        assert "[py:app.modules.catalog.gar_territory]" in body
        assert "failed parse" in body
        assert "GAR_TRACE_MARKER" in body
        assert "Traceback (most recent call last)" in body
    finally:
        end_sync_debug_log()


def test_catalog_and_pstn_debug_mirrored(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    begin_sync_debug_log(uuid.uuid4())
    try:
        logging.getLogger("app.modules.catalog.geo_policy").debug("GEO_DEBUG_MARKER")
        logging.getLogger("app.modules.pstn_inn_cache").debug("PSTN_DEBUG_MARKER")
        body = path.read_text(encoding="utf-8")
        assert "GEO_DEBUG_MARKER" in body
        assert "PSTN_DEBUG_MARKER" in body
        assert "  DEBUG  " in body
    finally:
        end_sync_debug_log()


def test_is_unusual_gar_territory():
    assert is_unusual_gar_territory(None) is False
    assert is_unusual_gar_territory("Москва|Московская область") is False
    assert is_unusual_gar_territory("Новосибирск|Новосибирская область") is False
    assert is_unusual_gar_territory(LONG_GEO) is True
    assert is_unusual_gar_territory("город|а, б, в, г") is True


def test_geo_dump_writes_full_gar_without_ellipsis(tmp_path: Path, monkeypatch):
    path = tmp_path / "sync_latest.log"
    _patch_log_path(monkeypatch, path)

    db = MagicMock()
    db.execute.return_value.all.return_value = [(LONG_GEO, LONG_GEO, 17)]
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(
            operator="ПАО «МТС»",
            abc="900",
            range_start=0,
            range_end=99999,
            gar_territory=LONG_GEO,
        ),
        SimpleNamespace(
            operator="Городской",
            abc="383",
            range_start=1,
            range_end=2,
            gar_territory="Новосибирск|Новосибирская область",
        ),
    ]

    begin_sync_debug_log(uuid.uuid4())
    try:
        dump_sync_geo_diagnostics(db)
        body = path.read_text(encoding="utf-8")
        assert "=== CATALOG GEO DISTINCT count=1 ===" in body
        assert "=== UNUSUAL PSTN GAR count=1 ===" in body
        assert body.count(LONG_GEO) >= 2
        assert "ПАО «МТС»" in body
        assert '"abc": "900"' in body
        assert "Новосибирск|Новосибирская область" not in body
        assert "..." not in body
    finally:
        end_sync_debug_log()
