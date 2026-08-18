"""Async XLSX export jobs + full-catalog snapshots after sync."""

from __future__ import annotations

import hmac
import json
import logging
import secrets
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
# Filtered job_*.xlsx writers only (not snapshot rebuilds).
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
    phase: str = "queued"
    ticket: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    filters: dict[str, list[str]] = field(default_factory=dict)
    number_local_q: str | None = None
    sort_by: str | None = DEFAULT_SORT_BY
    sort_dir: str = DEFAULT_SORT_DIR

    def to_public(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "inventory_kind": self.inventory_kind.value,
            "status": self.status,
            "phase": self.phase,
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
        if self.status == "ready" and self.ticket:
            out["ticket"] = self.ticket
        return out


@dataclass
class _KindWriter:
    kind: InventoryKind
    status: str = "writing"
    phase: str = "writing"
    rows_done: int = 0
    rows_total: int | None = None
    owner_job_id: str | None = None
    waiter_ids: list[str] = field(default_factory=list)
    done: threading.Event = field(default_factory=threading.Event)
    result_ok: bool = False
    error: str | None = None


_snapshot_writers: dict[InventoryKind, _KindWriter] = {}


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


def job_ticket_matches(job: ExportJob, ticket: str | None) -> bool:
    if not ticket or not job.ticket:
        return False
    given = ticket.strip()
    expected = job.ticket
    if len(given) != len(expected):
        return False
    return hmac.compare_digest(given, expected)


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
        and meta.get("max_updated_at") == fingerprint.get("max_updated_at")
        and meta.get("columns_schema") == fingerprint.get("columns_schema")
        and meta.get("sort_by") == DEFAULT_SORT_BY
        and meta.get("sort_dir") == DEFAULT_SORT_DIR
    )


def _new_ticket() -> str:
    return secrets.token_urlsafe(24)


def _filename_for(kind: InventoryKind) -> str:
    return "free_numbers.xlsx" if kind == InventoryKind.free else "purchased_numbers.xlsx"


def _fingerprint(kind: InventoryKind) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return catalog_fingerprint(db, kind)
    finally:
        db.close()


def _store_ready_snapshot_job(
    *,
    kind: InventoryKind,
    filename: str,
    filters: dict[str, list[str]],
    number_local_q: str | None,
    sort_by: str | None,
    sort_dir: str,
    fingerprint: dict[str, Any],
) -> ExportJob:
    job_id = uuid.uuid4().hex
    xlsx_path, _ = snapshot_paths(kind)
    count = int(fingerprint.get("count") or 0)
    job = ExportJob(
        id=job_id,
        inventory_kind=kind,
        status="ready",
        phase="ready",
        filename=filename,
        path=str(xlsx_path),
        from_snapshot=True,
        ticket=_new_ticket(),
        rows_done=count,
        rows_total=count,
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


def _writer_job_ids(writer: _KindWriter) -> list[str]:
    ids: list[str] = []
    if writer.owner_job_id:
        ids.append(writer.owner_job_id)
    ids.extend(writer.waiter_ids)
    return ids


def _update_snapshot_progress(
    kind: InventoryKind,
    done: int,
    tot: int | None,
    phase: str = "writing",
) -> None:
    with _lock:
        writer = _snapshot_writers.get(kind)
        if writer is None:
            return
        writer.rows_done = done
        if tot is not None:
            writer.rows_total = tot
        if phase:
            writer.phase = phase
            writer.status = phase if phase in {"writing", "closing"} else writer.status
        for jid in _writer_job_ids(writer):
            job = _jobs.get(jid)
            if job is None or job.status not in {"queued", "running"}:
                continue
            job.status = "running"
            job.rows_done = done
            if tot is not None:
                job.rows_total = tot
            job.phase = phase


def _finish_snapshot_writer(
    kind: InventoryKind,
    *,
    ok: bool,
    rows: int = 0,
    path: str | None = None,
    error: str | None = None,
) -> None:
    with _lock:
        writer = _snapshot_writers.get(kind)
        if writer is None:
            return
        writer.result_ok = ok
        writer.error = error
        writer.rows_done = rows
        writer.rows_total = rows if ok else writer.rows_total
        writer.phase = "ready" if ok else "failed"
        now = time.time()
        for jid in _writer_job_ids(writer):
            job = _jobs.get(jid)
            if job is None:
                continue
            if ok:
                job.status = "ready"
                job.phase = "ready"
                job.path = path
                job.from_snapshot = True
                job.ticket = _new_ticket()
                job.rows_done = rows
                job.rows_total = rows
                job.finished_at = now
                job.error = None
            else:
                job.status = "failed"
                job.phase = "failed"
                job.error = error
                job.finished_at = now
        writer.done.set()
        if _snapshot_writers.get(kind) is writer:
            del _snapshot_writers[kind]


def _run_snapshot_write(kind: InventoryKind, fingerprint: dict[str, Any]) -> dict[str, Any]:
    xlsx_path, meta_path = snapshot_paths(kind)
    tmp_path = xlsx_path.with_suffix(".xlsx.tmp")
    try:
        def _progress(done: int, tot: int | None, phase: str = "writing") -> None:
            _update_snapshot_progress(kind, done, tot, phase)

        rows = export_xlsx_job(
            inventory_kind=kind,
            path=str(tmp_path),
            filters=None,
            number_local_q=None,
            sort_by=DEFAULT_SORT_BY,
            sort_dir=DEFAULT_SORT_DIR,
            on_progress=_progress,
            rows_total=int(fingerprint.get("count") or 0),
        )
        tmp_path.replace(xlsx_path)
        meta = {
            **fingerprint,
            "row_count": rows,
            "sort_by": DEFAULT_SORT_BY,
            "sort_dir": DEFAULT_SORT_DIR,
            "built_at": datetime.now(UTC).isoformat(),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        _finish_snapshot_writer(kind, ok=True, rows=rows, path=str(xlsx_path))
        logger.warning(
            "Export snapshot rebuilt kind=%s rows=%s path=%s",
            kind.value,
            rows,
            xlsx_path,
        )
        return {"ok": True, "rows": rows, **fingerprint}
    except Exception as exc:
        logger.exception("Export snapshot rebuild failed kind=%s", kind.value)
        tmp_path.unlink(missing_ok=True)
        err = str(exc)[:500]
        _finish_snapshot_writer(kind, ok=False, error=err[:300])
        return {"ok": False, "error": err[:300]}


def _ensure_snapshot_written(kind: InventoryKind) -> dict[str, Any]:
    """Single writer per kind. If already writing, wait for that writer."""
    fp = _fingerprint(kind)
    with _lock:
        existing = _snapshot_writers.get(kind)
        if existing is not None and not existing.done.is_set():
            wait_on = existing
        else:
            wait_on = None
            writer = _KindWriter(
                kind=kind,
                rows_total=int(fp.get("count") or 0),
            )
            _snapshot_writers[kind] = writer
    if wait_on is not None:
        wait_on.done.wait(timeout=3600)
        if not wait_on.result_ok:
            return {"ok": False, "error": wait_on.error or "snapshot failed"}
        return {"ok": True, "rows": wait_on.rows_done}
    return _run_snapshot_write(kind, fp)


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
    filename = _filename_for(inventory_kind)
    default_query = is_default_export_query(
        filters=filters,
        number_local_q=number_local_q,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    if default_query:
        fp = _fingerprint(inventory_kind)
        if snapshot_is_fresh(inventory_kind, fp):
            return _store_ready_snapshot_job(
                kind=inventory_kind,
                filename=filename,
                filters=filters,
                number_local_q=number_local_q,
                sort_by=sort_by,
                sort_dir=sort_dir,
                fingerprint=fp,
            )

        start_thread = False
        with _lock:
            _cleanup_expired_jobs_locked()
            if snapshot_is_fresh(inventory_kind, fp):
                pass
            else:
                job_id = uuid.uuid4().hex
                job = ExportJob(
                    id=job_id,
                    inventory_kind=inventory_kind,
                    status="running",
                    phase="writing",
                    filename=filename,
                    from_snapshot=True,
                    rows_done=0,
                    rows_total=int(fp.get("count") or 0),
                    filters=filters,
                    number_local_q=number_local_q,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                )
                writer = _snapshot_writers.get(inventory_kind)
                if writer is not None and not writer.done.is_set():
                    writer.waiter_ids.append(job_id)
                    job.rows_done = writer.rows_done
                    job.rows_total = writer.rows_total or job.rows_total
                    job.phase = writer.phase
                    _jobs[job_id] = job
                    return job
                writer = _KindWriter(
                    kind=inventory_kind,
                    owner_job_id=job_id,
                    rows_total=job.rows_total,
                )
                _snapshot_writers[inventory_kind] = writer
                _jobs[job_id] = job
                start_thread = True
        if start_thread:
            thread = threading.Thread(
                target=_run_snapshot_write,
                args=(inventory_kind, fp),
                name=f"export-snapshot-{inventory_kind.value}",
                daemon=True,
            )
            thread.start()
            return job
        return _store_ready_snapshot_job(
            kind=inventory_kind,
            filename=filename,
            filters=filters,
            number_local_q=number_local_q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            fingerprint=fp,
        )

    with _lock:
        _cleanup_expired_jobs_locked()
        global _active_builds
        if _active_builds >= _MAX_CONCURRENT:
            raise RuntimeError(
                "Экспорт с фильтрами уже выполняется — дождитесь окончания текущего задания"
            )
        job_id = uuid.uuid4().hex
        job = ExportJob(
            id=job_id,
            inventory_kind=inventory_kind,
            status="queued",
            phase="queued",
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
            job.phase = "writing"
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

        def _progress(done: int, tot: int | None, phase: str = "writing") -> None:
            with _lock:
                j = _jobs.get(job_id)
                if j is None:
                    return
                j.rows_done = done
                if tot is not None:
                    j.rows_total = tot
                if phase:
                    j.phase = phase

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
            job.phase = "ready"
            job.path = str(out_path)
            job.ticket = _new_ticket()
            job.rows_done = total
            job.rows_total = total
            job.finished_at = time.time()
    except Exception as exc:
        logger.exception("Export job %s failed", job_id)
        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "failed"
                job.phase = "failed"
                job.error = str(exc)[:500]
                job.finished_at = time.time()
        out_path.unlink(missing_ok=True)
    finally:
        with _lock:
            _active_builds = max(0, _active_builds - 1)


def rebuild_catalog_snapshots() -> dict[str, Any]:
    """Rebuild free/purchased full-catalog XLSX snapshots (blocking, per-kind)."""
    results: dict[str, Any] = {}
    for kind in (InventoryKind.free, InventoryKind.purchased):
        results[kind.value] = _ensure_snapshot_written(kind)
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
    try:
        # Don't occupy the filtered-export slot; per-kind writers serialize themselves.
        rebuild_catalog_snapshots()
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
