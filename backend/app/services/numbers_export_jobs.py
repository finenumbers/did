"""Async XLSX export jobs + full-catalog snapshots after sync."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.enums import InventoryKind
from app.services.numbers_export import (
    DEFAULT_SORT_BY,
    DEFAULT_SORT_DIR,
    catalog_fingerprint,
    export_xlsx_job,
    is_default_export_query,
    NumbersExportService,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: dict[str, ExportJob] = {}
_active_builds = 0
_MAX_CONCURRENT = 1
_JOB_TTL_SEC = 60 * 60
_SNAPSHOT_NAMES = {
    InventoryKind.free: "free_latest",
    InventoryKind.purchased: "purchased_latest",
}


@dataclass
class ExportJob:
    id: str
    inventory_kind: InventoryKind
    status: str  # queued | running | ready | failed
    path: str | None = None
    filename: str = "export.xlsx"
    error: str | None = None
    rows_done: int = 0
    rows_total: int | None = None
    from_snapshot: bool = False
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    filters: dict[str, list[str]] = field(default_factory=dict)
    number_local_q: str | None = None
    sort_by: str | None = DEFAULT_SORT_BY
    sort_dir: str = DEFAULT_SORT_DIR

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "inventory_kind": self.inventory_kind.value,
            "status": self.status,
            "rows_done": self.rows_done,
            "rows_total": self.rows_total,
            "from_snapshot": self.from_snapshot,
            "error": self.error,
            "filename": self.filename,
            "created_at": datetime.fromtimestamp(self.created_at, UTC).isoformat(),
            "finished_at": (
                datetime.fromtimestamp(self.finished_at, UTC).isoformat()
                if self.finished_at
                else None
            ),
        }


def exports_dir() -> Path:
    path = Path(get_settings().numbers_export_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_paths(kind: InventoryKind) -> tuple[Path, Path]:
    base = _SNAPSHOT_NAMES[kind]
    d = exports_dir()
    return d / f"{base}.xlsx", d / f"{base}.meta.json"


def _cleanup_expired_jobs_locked() -> None:
    now = time.time()
    expired = [jid for jid, job in _jobs.items() if now - job.created_at > _JOB_TTL_SEC]
    for jid in expired:
        job = _jobs.pop(jid)
        if job.path and not job.from_snapshot:
            try:
                Path(job.path).unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to delete expired export job file %s", job.path)


def get_job(job_id: str) -> ExportJob | None:
    with _lock:
        _cleanup_expired_jobs_locked()
        return _jobs.get(job_id)


def read_snapshot_meta(kind: InventoryKind) -> dict[str, Any] | None:
    _xlsx, meta_path = snapshot_paths(kind)
    if not meta_path.is_file() or not _xlsx.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read export snapshot meta %s", meta_path)
        return None


def snapshot_is_fresh(kind: InventoryKind, fingerprint: dict[str, Any]) -> bool:
    meta = read_snapshot_meta(kind)
    if not meta:
        return False
    xlsx_path, _ = snapshot_paths(kind)
    if not xlsx_path.is_file():
        return False
    return (
        meta.get("count") == fingerprint.get("count")
        and meta.get("max_last_seen_at") == fingerprint.get("max_last_seen_at")
        and meta.get("sort_by") == DEFAULT_SORT_BY
        and meta.get("sort_dir") == DEFAULT_SORT_DIR
    )


def create_export_job(
    *,
    inventory_kind: InventoryKind,
    filters: dict[str, list[str]] | None = None,
    number_local_q: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = DEFAULT_SORT_DIR,
) -> ExportJob:
    filters = filters or {}
    sort_by = sort_by or DEFAULT_SORT_BY
    sort_dir = (sort_dir or DEFAULT_SORT_DIR).lower()
    filename = (
        "free_numbers.xlsx"
        if inventory_kind == InventoryKind.free
        else "purchased_numbers.xlsx"
    )

    # Snapshot check outside lock (DB I/O)
    if is_default_export_query(
        filters=filters,
        number_local_q=number_local_q,
        sort_by=sort_by,
        sort_dir=sort_dir,
    ):
        db = SessionLocal()
        try:
            fp = catalog_fingerprint(db, inventory_kind)
        finally:
            db.close()
        if snapshot_is_fresh(inventory_kind, fp):
            job_id = uuid.uuid4().hex
            xlsx_path, _ = snapshot_paths(inventory_kind)
            job = ExportJob(
                id=job_id,
                inventory_kind=inventory_kind,
                status="ready",
                filename=filename,
                path=str(xlsx_path),
                from_snapshot=True,
                rows_done=int(fp.get("count") or 0),
                rows_total=int(fp.get("count") or 0),
                finished_at=time.time(),
                filters=filters,
                number_local_q=number_local_q,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            with _lock:
                _cleanup_expired_jobs_locked()
                _jobs[job_id] = job
            return job

    with _lock:
        _cleanup_expired_jobs_locked()
        global _active_builds
        if _active_builds >= _MAX_CONCURRENT:
            raise RuntimeError(
                "Экспорт уже выполняется — дождитесь окончания текущего задания"
            )
        job_id = uuid.uuid4().hex
        job = ExportJob(
            id=job_id,
            inventory_kind=inventory_kind,
            status="queued",
            filename=filename,
            filters=filters,
            number_local_q=number_local_q,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        _jobs[job_id] = job
        _active_builds += 1

    thread = threading.Thread(
        target=_run_job,
        args=(job_id,),
        name=f"export-xlsx-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return job


def _run_job(job_id: str) -> None:
    global _active_builds
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        with _lock:
            _active_builds = max(0, _active_builds - 1)
        return

    out_path = exports_dir() / f"job_{job_id}.xlsx"
    try:
        with _lock:
            job.status = "running"
        db = SessionLocal()
        try:
            total = NumbersExportService(db).count_filtered(
                inventory_kind=job.inventory_kind,
                filters=job.filters,
                number_local_q=job.number_local_q,
            )
        finally:
            db.close()
        with _lock:
            job.rows_total = total

        def _progress(done: int, tot: int | None) -> None:
            with _lock:
                j = _jobs.get(job_id)
                if j is None:
                    return
                j.rows_done = done
                if tot is not None:
                    j.rows_total = tot

        export_xlsx_job(
            inventory_kind=job.inventory_kind,
            path=str(out_path),
            filters=job.filters,
            number_local_q=job.number_local_q,
            sort_by=job.sort_by,
            sort_dir=job.sort_dir,
            on_progress=_progress,
            rows_total=total,
        )
        with _lock:
            job = _jobs.get(job_id)
            if job is None:
                out_path.unlink(missing_ok=True)
                return
            job.status = "ready"
            job.path = str(out_path)
            job.rows_done = total
            job.rows_total = total
            job.finished_at = time.time()
    except Exception as exc:
        logger.exception("Export job %s failed", job_id)
        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "failed"
                job.error = str(exc)[:500]
                job.finished_at = time.time()
        out_path.unlink(missing_ok=True)
    finally:
        with _lock:
            _active_builds = max(0, _active_builds - 1)


def rebuild_catalog_snapshots() -> dict[str, Any]:
    """Rebuild free/purchased full-catalog XLSX snapshots (blocking)."""
    results: dict[str, Any] = {}
    for kind in (InventoryKind.free, InventoryKind.purchased):
        xlsx_path, meta_path = snapshot_paths(kind)
        tmp_path = xlsx_path.with_suffix(".xlsx.tmp")
        try:
            db = SessionLocal()
            try:
                fp = catalog_fingerprint(db, kind)
                svc = NumbersExportService(db)
                rows = svc.export_xlsx(
                    inventory_kind=kind,
                    path=tmp_path,
                    filters=None,
                    number_local_q=None,
                    sort_by=DEFAULT_SORT_BY,
                    sort_dir=DEFAULT_SORT_DIR,
                    rows_total=int(fp.get("count") or 0),
                )
            finally:
                db.close()
            tmp_path.replace(xlsx_path)
            meta = {
                **fp,
                "row_count": rows,
                "sort_by": DEFAULT_SORT_BY,
                "sort_dir": DEFAULT_SORT_DIR,
                "built_at": datetime.now(UTC).isoformat(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            results[kind.value] = {"ok": True, "rows": rows, **fp}
            logger.warning(
                "Export snapshot rebuilt kind=%s rows=%s path=%s",
                kind.value,
                rows,
                xlsx_path,
            )
        except Exception as exc:
            logger.exception("Export snapshot rebuild failed kind=%s", kind.value)
            tmp_path.unlink(missing_ok=True)
            results[kind.value] = {"ok": False, "error": str(exc)[:300]}
    return results


def schedule_snapshot_rebuild() -> None:
    """Fire-and-forget snapshot rebuild after sync."""
    thread = threading.Thread(
        target=_safe_rebuild_snapshots,
        name="export-snapshots",
        daemon=True,
    )
    thread.start()


def _safe_rebuild_snapshots() -> None:
    global _active_builds
    try:
        # Avoid fighting an interactive export for CPU: wait briefly for slot
        for _ in range(120):
            with _lock:
                busy = _active_builds > 0
            if not busy:
                break
            time.sleep(1)
        with _lock:
            _active_builds += 1
        try:
            rebuild_catalog_snapshots()
        finally:
            with _lock:
                _active_builds = max(0, _active_builds - 1)
    except Exception:
        logger.exception("Snapshot rebuild thread crashed")


def copy_job_file_for_download(job: ExportJob) -> Path | None:
    """Return path to serve; snapshot path is shared, job path is owned."""
    if not job.path:
        return None
    path = Path(job.path)
    if not path.is_file():
        return None
    return path
