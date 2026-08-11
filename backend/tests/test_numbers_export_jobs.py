"""Tests for async XLSX export jobs and snapshots."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import xlsxwriter
from openpyxl import load_workbook

from app.models.enums import InventoryKind
from app.services import numbers_export_jobs as jobs
from app.services.numbers_export import is_default_export_query


def test_is_default_export_query():
    assert is_default_export_query(
        filters=None, number_local_q=None, sort_by="abc_code", sort_dir="asc"
    )
    assert not is_default_export_query(
        filters={"region_name": ["x"]},
        number_local_q=None,
        sort_by="abc_code",
        sort_dir="asc",
    )
    assert not is_default_export_query(
        filters=None, number_local_q="123", sort_by="abc_code", sort_dir="asc"
    )


def test_export_job_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NUMBERS_EXPORT_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(jobs, "exports_dir", lambda: tmp_path)

    def fake_run_job(job_id: str) -> None:
        with jobs._lock:
            job = jobs._jobs.get(job_id)
            if job is None:
                jobs._active_builds = max(0, jobs._active_builds - 1)
                return
            job.status = "running"
            job.rows_total = 1
        out = tmp_path / f"job_{job_id}.xlsx"
        wb = xlsxwriter.Workbook(str(out))
        ws = wb.add_worksheet("Свободные")
        ws.write(0, 0, "Провайдер")
        ws.write(1, 0, "runexis")
        wb.close()
        with jobs._lock:
            job = jobs._jobs.get(job_id)
            if job is not None:
                job.status = "ready"
                job.path = str(out)
                job.rows_done = 1
                job.rows_total = 1
                job.finished_at = time.time()
            jobs._active_builds = max(0, jobs._active_builds - 1)

    monkeypatch.setattr(jobs, "_run_job", fake_run_job)

    job = jobs.create_export_job(
        inventory_kind=InventoryKind.free,
        filters={"abc_code": ["301"]},
        number_local_q=None,
        sort_by="abc_code",
        sort_dir="asc",
    )
    for _ in range(50):
        j = jobs.get_job(job.id)
        assert j is not None
        if j.status in {"ready", "failed"}:
            break
        time.sleep(0.05)
    j = jobs.get_job(job.id)
    assert j is not None
    assert j.status == "ready"
    assert j.path and Path(j.path).is_file()

    wb = load_workbook(j.path, read_only=True)
    try:
        rows = list(wb.active.iter_rows(values_only=True))
        assert rows[0][0] == "Провайдер"
        assert rows[1][0] == "runexis"
    finally:
        wb.close()

    get_settings.cache_clear()


def test_snapshot_fast_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NUMBERS_EXPORT_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(jobs, "exports_dir", lambda: tmp_path)

    xlsx_path = tmp_path / "free_latest.xlsx"
    meta_path = tmp_path / "free_latest.meta.json"
    wb = xlsxwriter.Workbook(str(xlsx_path))
    ws = wb.add_worksheet("Свободные")
    ws.write(0, 0, "Провайдер")
    wb.close()
    meta_path.write_text(
        '{"count": 10, "max_last_seen_at": "2026-01-01T00:00:00+00:00",'
        ' "sort_by": "abc_code", "sort_dir": "asc"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        jobs,
        "catalog_fingerprint",
        lambda db, kind: {
            "count": 10,
            "max_last_seen_at": "2026-01-01T00:00:00+00:00",
        },
    )

    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("should use snapshot")

    monkeypatch.setattr(jobs, "_run_job", boom)

    job = jobs.create_export_job(
        inventory_kind=InventoryKind.free,
        filters=None,
        number_local_q=None,
        sort_by="abc_code",
        sort_dir="asc",
    )
    assert job.status == "ready"
    assert job.from_snapshot is True
    assert job.rows_total == 10
    assert called["n"] == 0
    assert job.path == str(xlsx_path)

    get_settings.cache_clear()
