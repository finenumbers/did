"""Unified multi-provider sync with stage progress for the Sync UI."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, joinedload

from app.core.db import SessionLocal, dispose_engine_pool
from app.models.enums import ProviderCode, SyncJobStatus, SyncJobType, SyncLogLevel
from app.models.providers import Provider
from app.models.sync import SyncJob, SyncRun
from app.modules.sync_engine.dropped_export import (
    begin_dropped_export,
    end_dropped_export,
    get_collector,
    write_dropped_xlsx,
)
from app.modules.sync_engine.locks import (
    SYNC_LOCK_KEY,
    acquire_sync_lock,
    advisory_unlock_conn,
    ping_lock_conn,
)
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.progress import (
    SyncAborted,
    SyncProgressTracker,
    apply_progress_abort,
    build_initial_progress,
    build_stage_timings,
    stage_for_provider_phase,
    stage_status,
)
from app.modules.sync_engine.run_file_log import begin_sync_debug_log, end_sync_debug_log
from app.modules.sync_engine.run_logging import log_run
from app.modules.sync_engine.safety import build_catalog_checksum, build_inventory_summary
from app.modules.sync_engine.service import SyncService
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderCapabilityLimitedError, ProviderError
from app.providers.finenumbers.enrich import enrich_catalog_operators
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)

LOCK_KEEPALIVE_SECONDS = 30

STALE_RUNNING_MINUTES = 180
STALE_PENDING_MINUTES = 30
PROVIDER_ORDER = (
    ProviderCode.sipout,
    ProviderCode.runexis,
    ProviderCode.uis,
    ProviderCode.aurora,
    ProviderCode.exolve,
    ProviderCode.voximplant,
    ProviderCode.mcn,
    ProviderCode.finenumbers,
)
ACTIVE_STATUSES = (SyncJobStatus.pending, SyncJobStatus.running)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mark_stale_runs(db: Session) -> int:
    """Age-out pending always; age-out running only when sync advisory lock is free."""
    from app.modules.sync_engine.locks import SYNC_LOCK_KEY, advisory_unlock, try_advisory_lock

    cutoff_running = _now() - timedelta(minutes=STALE_RUNNING_MINUTES)
    cutoff_pending = _now() - timedelta(minutes=STALE_PENDING_MINUTES)
    pending = list(
        db.scalars(
            select(SyncRun).where(
                SyncRun.status == SyncJobStatus.pending,
                SyncRun.created_at < cutoff_pending,
            )
        ).all()
    )
    running = list(
        db.scalars(
            select(SyncRun).where(
                SyncRun.status == SyncJobStatus.running,
                SyncRun.started_at.is_not(None),
                SyncRun.started_at < cutoff_running,
            )
        ).all()
    )

    marked = 0
    for run in pending:
        reason = f"Marked stale: pending longer than {STALE_PENDING_MINUTES} minutes"
        run.status = SyncJobStatus.failed
        run.error_summary = reason
        run.finished_at = _now()
        apply_progress_abort(run, reason)
        log_run(db, run.id, SyncLogLevel.error, run.error_summary)
        marked += 1

    if running:
        if try_advisory_lock(db, SYNC_LOCK_KEY):
            try:
                for run in running:
                    # Re-check status in case reclaim raced; only fail still-running rows.
                    db.refresh(run)
                    if run.status != SyncJobStatus.running:
                        continue
                    reason = (
                        f"Marked stale: running longer than {STALE_RUNNING_MINUTES} minutes"
                    )
                    run.status = SyncJobStatus.failed
                    run.error_summary = reason
                    run.finished_at = _now()
                    apply_progress_abort(run, reason)
                    log_run(db, run.id, SyncLogLevel.error, run.error_summary)
                    marked += 1
            finally:
                try:
                    advisory_unlock(db, SYNC_LOCK_KEY)
                except Exception:
                    logger.exception("Failed to release lock after stale running mark")
        # else: live worker holds the lock — leave running rows alone

    if marked:
        db.commit()
    return marked


def reclaim_orphaned_running_runs(db: Session) -> int:
    """If a run is `running` but the sync advisory lock is free, the worker died — reclaim."""
    from app.modules.sync_engine.locks import SYNC_LOCK_KEY, advisory_unlock, try_advisory_lock

    running = list(
        db.scalars(
            select(SyncRun).where(SyncRun.status == SyncJobStatus.running)
        ).all()
    )
    if not running:
        return 0
    if not try_advisory_lock(db, SYNC_LOCK_KEY):
        # Live sync holds the lock — leave running rows alone
        return 0
    reclaimed = 0
    try:
        for run in running:
            db.refresh(run)
            if run.status != SyncJobStatus.running:
                continue
            reason = "Marked orphan: running but sync lock was free"
            run.status = SyncJobStatus.failed
            run.error_summary = reason
            run.finished_at = _now()
            apply_progress_abort(run, reason)
            log_run(db, run.id, SyncLogLevel.error, run.error_summary)
            reclaimed += 1
        if reclaimed:
            db.commit()
    finally:
        try:
            advisory_unlock(db, SYNC_LOCK_KEY)
        except Exception:
            logger.exception("Failed to release lock after orphan reclaim")
    return reclaimed


def get_active_run(db: Session) -> SyncRun | None:
    reclaim_orphaned_running_runs(db)
    mark_stale_runs(db)
    return db.scalars(
        select(SyncRun)
        .where(SyncRun.status.in_(ACTIVE_STATUSES))
        .order_by(SyncRun.created_at.desc())
        .limit(1)
    ).first()


def get_latest_run(db: Session) -> SyncRun | None:
    reclaim_orphaned_running_runs(db)
    mark_stale_runs(db)
    return db.scalars(select(SyncRun).order_by(SyncRun.created_at.desc()).limit(1)).first()


def create_run(db: Session, *, triggered_by: str = "api") -> SyncRun:
    from sqlalchemy.exc import IntegrityError

    from app.modules.pstn_inn_cache.service import require_min_cache_ready

    require_min_cache_ready(db)
    if get_active_run(db) is not None:
        raise ProviderError(
            "Синхронизация уже выполняется",
            code="SYNC_ALREADY_RUNNING",
        )
    run = SyncRun(
        status=SyncJobStatus.pending,
        triggered_by=triggered_by,
        progress=build_initial_progress(),
        stats={},
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProviderError(
            "Синхронизация уже выполняется",
            code="SYNC_ALREADY_RUNNING",
        ) from exc
    db.refresh(run)
    return run


def _other_active_sync_run(db: Session, run_id: uuid.UUID) -> bool:
    """True if another pending/running SyncRun exists (excluding this run_id)."""
    return (
        db.scalar(
            select(SyncRun.id)
            .where(SyncRun.status.in_(ACTIVE_STATUSES), SyncRun.id != run_id)
            .limit(1)
        )
        is not None
    )


async def _lock_conn_keepalive(
    lock_conn: Connection,
    stop: asyncio.Event,
    gate: threading.Lock,
) -> None:
    """Keep the lock connection alive so idle TCP/Postgres timeouts do not drop the advisory lock."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=LOCK_KEEPALIVE_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.to_thread(_ping_lock_conn_gated, lock_conn, gate)
        except Exception:
            logger.exception("lock_conn keepalive failed; lock session may be dead")
            return


def _ping_lock_conn_gated(lock_conn: Connection, gate: threading.Lock) -> None:
    with gate:
        ping_lock_conn(lock_conn)


async def execute_unified_run(run_id: uuid.UUID) -> None:
    from app.modules.sync_engine.progress import SyncAborted, apply_progress_abort
    from app.modules.sync_engine.scheduler import _set_last_fired_date
    from zoneinfo import ZoneInfo

    # Hold SYNC_LOCK_KEY on a lock_engine Connection for the whole run. Never use a
    # Session for this: Session.commit() returns the connection to the main pool where
    # checkin runs pg_advisory_unlock_all() and reclaim would false-orphan the run.
    work_db = SessionLocal()
    lock_conn: Connection | None = None
    locked = False
    lock_gate = threading.Lock()
    stop_keepalive = asyncio.Event()
    keepalive_task: asyncio.Task[None] | None = None
    try:
        acquired, lock_conn, lock_err, main_disposed = acquire_sync_lock(
            other_active_run=lambda: _other_active_sync_run(work_db, run_id),
            dispose_main_pool=dispose_engine_pool,
        )
        if main_disposed:
            try:
                work_db.close()
            except Exception:
                logger.exception("Failed to close work_db after main pool dispose heal")
            work_db = SessionLocal()
        if not acquired:
            run = work_db.get(SyncRun, run_id)
            if run is not None and run.status in ACTIVE_STATUSES:
                run.status = SyncJobStatus.failed
                run.error_summary = lock_err or "Синхронизация уже выполняется (lock)"
                run.finished_at = _now()
                work_db.commit()
            return
        locked = True
        keepalive_task = asyncio.create_task(
            _lock_conn_keepalive(lock_conn, stop_keepalive, lock_gate),
            name=f"sync-lock-keepalive-{run_id}",
        )
        run = work_db.get(SyncRun, run_id)
        if run is not None and (run.triggered_by or "") == "schedule":
            day_key = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
            try:
                _set_last_fired_date(work_db, day_key)
            except Exception:
                logger.exception(
                    "Failed to mark schedule last_fired for run_id=%s; aborting run",
                    run_id,
                )
                run.status = SyncJobStatus.failed
                run.error_summary = "Failed to mark schedule last_fired"
                run.finished_at = _now()
                work_db.commit()
                return
        await _execute_unified_run(work_db, run_id)
    except SyncAborted as exc:
        logger.warning("Unified sync cooperatively aborted run_id=%s: %s", run_id, exc)
        try:
            work_db.rollback()
            run = work_db.get(SyncRun, run_id)
            if run is not None and run.status in ACTIVE_STATUSES:
                reason = str(exc) or "Sync aborted"
                run.status = SyncJobStatus.failed
                run.error_summary = reason
                run.finished_at = _now()
                apply_progress_abort(run, reason)
                work_db.commit()
        except Exception:
            work_db.rollback()
    except Exception:
        logger.exception("Unified sync crashed run_id=%s", run_id)
        try:
            work_db.rollback()
            run = work_db.get(SyncRun, run_id)
            if run is not None:
                run.status = SyncJobStatus.failed
                run.error_summary = "Unexpected sync failure"
                run.finished_at = _now()
                work_db.commit()
        except Exception:
            work_db.rollback()
    finally:
        stop_keepalive.set()
        if keepalive_task is not None:
            try:
                await keepalive_task
            except Exception:
                logger.exception("lock_conn keepalive task failed on shutdown")
        if locked and lock_conn is not None:
            with lock_gate:
                try:
                    advisory_unlock_conn(lock_conn, SYNC_LOCK_KEY)
                except Exception:
                    logger.exception(
                        "Failed to unlock sync lock; connection invalidated if possible"
                    )
        if lock_conn is not None:
            try:
                lock_conn.close()
            except Exception:
                logger.exception("Failed to close lock_conn")
        try:
            work_db.close()
        except Exception:
            logger.exception("Failed to close work_db")


def spawn_unified_run(run_id: uuid.UUID) -> None:
    """Run sync in a daemon thread so uvicorn reload/shutdown is not blocked."""

    def _runner() -> None:
        try:
            asyncio.run(execute_unified_run(run_id))
        except Exception:
            logger.exception("Unified sync thread crashed run_id=%s", run_id)

    threading.Thread(
        target=_runner,
        name=f"unified-sync-{run_id}",
        daemon=True,
    ).start()


async def _execute_unified_run(db: Session, run_id: uuid.UUID) -> None:
    run = db.get(SyncRun, run_id)
    if run is None:
        return

    tracker = SyncProgressTracker(db, run.id)
    run.status = SyncJobStatus.running
    run.started_at = _now()
    if not run.progress:
        run.progress = build_initial_progress()
    db.commit()

    begin_sync_debug_log(run.id, triggered_by=run.triggered_by)
    begin_dropped_export()
    dropped_meta: dict[str, Any] = {"available": False}
    dropped_written = False
    try:
        log_run(db, run.id, SyncLogLevel.info, "Unified sync started")

        tracker.begin("prepare", "Проверка подключений провайдеров")
        providers = {
            p.code: p
            for p in db.scalars(select(Provider).options(joinedload(Provider.connection))).all()
        }
        missing = [c.value for c in PROVIDER_ORDER if c not in providers]
        if missing:
            tracker.fail("prepare", f"Нет провайдеров в БД: {', '.join(missing)}")
            try:
                dropped_meta = write_dropped_xlsx()
                dropped_written = True
            except Exception:
                logger.exception("Failed to write sync dropped XLSX")
            _finish_run(db, run, SyncJobStatus.failed, f"Missing providers: {missing}")
            return
        tracker.end("prepare", "Провайдеры найдены")

        provider_failures: list[str] = []
        provider_ok = 0
        category_stats: dict[str, Any] = {}
        inventory_split_providers: list[str] = []

        for code in PROVIDER_ORDER:
            db.refresh(run)
            if run.status not in ACTIVE_STATUSES:
                raise SyncAborted(
                    run.error_summary
                    or f"Sync run stopped externally (status={run.status.value})"
                )
            provider = providers[code]
            if not provider.is_enabled:
                for phase in ("dictionaries", "free", "purchased"):
                    sid = stage_for_provider_phase(code.value, phase)
                    if sid:
                        tracker.skip(sid, "provider disabled")
                log_run(
                    db, run.id, SyncLogLevel.info, f"Provider {code.value}: skipped (disabled)"
                )
                continue
            # MCN without API key: skip cleanly (no key yet) — not a partial failure.
            if code == ProviderCode.mcn:
                auth = (
                    dict(provider.connection.auth_settings or {})
                    if provider.connection is not None
                    else {}
                )
                mcn_key = (auth.get("api_key") or "").strip()
                if not mcn_key:
                    for phase in ("dictionaries", "free", "purchased"):
                        sid = stage_for_provider_phase(code.value, phase)
                        if sid:
                            tracker.skip(sid, "нет API-ключа MCN")
                    log_run(
                        db,
                        run.id,
                        SyncLogLevel.info,
                        "Provider mcn: skipped (нет API-ключа)",
                    )
                    continue
            ok = await _sync_provider(
                db,
                run=run,
                tracker=tracker,
                provider=provider,
                category_stats=category_stats,
                inventory_split_providers=inventory_split_providers,
            )
            if ok:
                provider_ok += 1
            else:
                provider_failures.append(code.value)

        db.refresh(run)
        if run.status not in ACTIVE_STATUSES:
            raise SyncAborted(
                run.error_summary
                or f"Sync run stopped externally (status={run.status.value})"
            )

        # finalize before operator enrichment — enrich is the last sync stage
        tracker.begin("finalize", "Завершение")
        try:
            dropped_meta = write_dropped_xlsx()
            dropped_written = True
        except Exception:
            logger.exception("Failed to write sync dropped XLSX")
            dropped_meta = {"available": False, "error": "write_failed"}

        inventory_summary = build_inventory_summary(category_stats)
        catalog_checksum = build_catalog_checksum(category_stats)
        db.refresh(run)
        stage_timings = build_stage_timings(run.progress)
        summary = {
            "providers_ok": provider_ok,
            "providers_failed": provider_failures,
            "categories": category_stats,
            "inventory_summary": inventory_summary,
            "catalog_checksum": catalog_checksum,
            "dropped_export": dropped_meta,
            "stage_timings": stage_timings,
            "inventory_split": bool(inventory_split_providers),
            "inventory_split_providers": list(inventory_split_providers),
        }
        run.stats = summary
        db.commit()
        log_run(
            db,
            run.id,
            SyncLogLevel.info,
            (
                "Catalog checksum "
                f"sum_free={catalog_checksum.get('sum_free')} "
                f"sum_purchased={catalog_checksum.get('sum_purchased')} "
                f"sum_total={catalog_checksum.get('sum_total')} "
                f"enrich_rows_scanned={catalog_checksum.get('enrich_rows_scanned')} "
                f"enrich_matches_catalog={catalog_checksum.get('enrich_matches_catalog')}"
            ),
            catalog_checksum,
        )
        timing_compact = [
            {
                "id": t.get("id"),
                "status": t.get("status"),
                "duration_s": t.get("duration_s"),
            }
            for t in stage_timings
            if t.get("duration_s") is not None
        ]
        log_run(
            db,
            run.id,
            SyncLogLevel.info,
            f"Stage timings count={len(timing_compact)}",
            {"stage_timings": timing_compact},
        )
        tracker.end(
            "finalize",
            f"ok={provider_ok}, failed={len(provider_failures)}",
        )

        await _run_operator_enrichment(
            db,
            run=run,
            tracker=tracker,
            category_stats=category_stats,
            only_missing=False,
        )
        # Rebuild checksum after enrich so enrich_rows_scanned / enrich_matches_catalog
        # reflect real PSTN stats (including partial-fail details when present).
        if "operator_enrichment" in category_stats:
            catalog_checksum = build_catalog_checksum(category_stats)
            db.refresh(run)
            summary = dict(run.stats or summary)
            summary["categories"] = category_stats
            summary["catalog_checksum"] = catalog_checksum
            summary["inventory_summary"] = build_inventory_summary(category_stats)
            run.stats = summary
            db.commit()
            log_run(
                db,
                run.id,
                SyncLogLevel.info,
                (
                    "Catalog checksum after enrich "
                    f"sum_free={catalog_checksum.get('sum_free')} "
                    f"sum_purchased={catalog_checksum.get('sum_purchased')} "
                    f"sum_total={catalog_checksum.get('sum_total')} "
                    f"enrich_rows_scanned={catalog_checksum.get('enrich_rows_scanned')} "
                    f"enrich_matches_catalog={catalog_checksum.get('enrich_matches_catalog')}"
                ),
                catalog_checksum,
            )
        # Always re-apply RTU after enrich — even if enrichment failed: batches may
        # already be committed, and skipping would leave stale Своя/Внешняя flags.
        # Finenumbers labels depend on final (post-enrich) operator.
        fn_cats = category_stats.get("finenumbers")
        purch_stats = (
            fn_cats.get("purchased_numbers") if isinstance(fn_cats, dict) else None
        )
        if isinstance(purch_stats, dict) and "reg_keys" in purch_stats:
            from app.modules.sync_engine.persist import apply_rtu_connected_flags

            rtu_stats = apply_rtu_connected_flags(
                db, reg_keys=set(purch_stats.get("reg_keys") or [])
            )
            purch_stats.update(rtu_stats)
            db.commit()
            log_run(
                db,
                run.id,
                SyncLogLevel.info,
                (
                    "RTU flags re-applied after operator enrichment "
                    f"own={rtu_stats.get('rtu_own')} "
                    f"external={rtu_stats.get('rtu_external')} "
                    f"not_connected={rtu_stats.get('rtu_not_connected')}"
                ),
                rtu_stats,
            )
        db.refresh(run)
        summary = dict(run.stats or summary)
        summary["categories"] = category_stats
        summary["stage_timings"] = build_stage_timings(run.progress)
        run.stats = summary
        db.commit()

        if provider_failures and provider_ok == 0:
            status = SyncJobStatus.failed
            err = "All providers failed: " + ", ".join(provider_failures)
        elif provider_failures:
            status = SyncJobStatus.partial
            err = "Partial: failed " + ", ".join(provider_failures)
        else:
            status = SyncJobStatus.success
            err = None

        db.refresh(run)
        if (
            stage_status(run.progress, "operator_enrichment") == "failed"
            and status == SyncJobStatus.success
        ):
            status = SyncJobStatus.partial
            err = "operator enrichment failed"

        _finish_run(db, run, status, err)
        log_run(
            db,
            run.id,
            SyncLogLevel.info if status == SyncJobStatus.success else SyncLogLevel.warning,
            f"Unified sync finished status={status.value}",
            summary,
        )
        # Rebuild full-catalog XLSX snapshots for fast unfiltered export downloads.
        if status in (SyncJobStatus.success, SyncJobStatus.partial) and provider_ok > 0:
            try:
                from app.services.numbers_export_jobs import schedule_snapshot_rebuild

                schedule_snapshot_rebuild()
                log_run(
                    db,
                    run.id,
                    SyncLogLevel.info,
                    "Scheduled catalog XLSX snapshot rebuild",
                )
            except Exception:
                logger.exception("Failed to schedule catalog XLSX snapshot rebuild")
    finally:
        if not dropped_written:
            try:
                collector = get_collector()
                if collector and collector.rows:
                    write_dropped_xlsx()
            except Exception:
                logger.exception("Best-effort dropped XLSX write on sync exit failed")
        end_dropped_export()
        try:
            db.refresh(run)
            end_sync_debug_log(
                status=run.status.value if run.status else None,
                error_summary=run.error_summary,
            )
        except Exception:
            logger.exception("Failed to close sync debug log")
            end_sync_debug_log()


def _finish_run(
    db: Session,
    run: SyncRun,
    status: SyncJobStatus,
    error_summary: str | None,
) -> None:
    run.status = status
    run.error_summary = error_summary
    run.finished_at = _now()
    db.commit()


async def _sync_provider(
    db: Session,
    *,
    run: SyncRun,
    tracker: SyncProgressTracker,
    provider: Provider,
    category_stats: dict[str, Any],
    inventory_split_providers: list[str],
) -> bool:
    code = provider.code
    adapter = get_provider(code)
    caps = adapter.capabilities()

    if code != ProviderCode.finenumbers and not caps.get("purchased_numbers", {}).get("supported"):
        stage = stage_for_provider_phase(code.value, "purchased")
        if stage:
            tracker.skip(stage, "capability not supported")

    if code == ProviderCode.aurora:
        mode = SyncMode.free_only
        job_type = SyncJobType.free_only
    elif code == ProviderCode.finenumbers:
        mode = SyncMode.full
        job_type = SyncJobType.full
    else:
        mode = SyncMode.full
        job_type = SyncJobType.full

    job = SyncJob(
        provider_id=provider.id,
        job_type=job_type,
        status=SyncJobStatus.pending,
        triggered_by=f"unified:{run.id}",
        stats={
            "mode": mode.value,
            "sync_run_id": str(run.id),
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_run(db, run.id, SyncLogLevel.info, f"Provider {code.value}: job {job.id} started")

    async def phase_hook(
        phase: str,
        event: str,
        detail: str = "",
        *,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        stage_id = stage_for_provider_phase(code.value, phase)
        if not stage_id:
            return
        if event == "begin":
            tracker.begin(stage_id, detail or "")
        elif event == "progress":
            tracker.progress(
                stage_id,
                detail=detail or "",
                substage=detail or "",
                current=current,
                total=total,
                unit="numbers",
            )
        elif event == "end":
            tracker.end(stage_id, detail or "")
        elif event == "skip":
            tracker.skip(stage_id, detail or "")
        elif event == "fail":
            tracker.fail(stage_id, detail or "failed")

    try:
        service = SyncService(db)
        job = await service.run_job_async(
            job.id,
            phase_hook=phase_hook,
        )
    except SyncAborted:
        raise
    except ProviderCapabilityLimitedError as exc:
        log_run(db, run.id, SyncLogLevel.error, f"{code.value}: capability limited: {exc}")
        _fail_remaining_provider_stages(db, tracker, code.value, str(exc))
        return False
    except Exception as exc:
        log_run(db, run.id, SyncLogLevel.error, f"{code.value}: {exc}")
        _fail_remaining_provider_stages(db, tracker, code.value, str(exc))
        return False

    db.refresh(run)
    category_stats[code.value] = (job.stats or {}).get("categories") or {}
    if (job.stats or {}).get("inventory_split"):
        inventory_split_providers.append(code.value)

    if job.status == SyncJobStatus.failed:
        log_run(
            db,
            run.id,
            SyncLogLevel.error,
            f"{code.value} job failed: {job.error_summary}",
        )
        _fail_remaining_provider_stages(
            db, tracker, code.value, job.error_summary or "failed"
        )
        return False

    if code not in (ProviderCode.finenumbers, ProviderCode.aurora):
        for phase in ("dictionaries", "free", "purchased"):
            sid = stage_for_provider_phase(code.value, phase)
            if not sid:
                continue
            st = stage_status(run.progress, sid)
            if st == "pending":
                if phase == "purchased" and not caps.get("purchased_numbers", {}).get(
                    "supported"
                ):
                    tracker.skip(sid, "capability not supported")

    if job.status == SyncJobStatus.partial:
        log_run(db, run.id, SyncLogLevel.warning, f"{code.value} completed with limitations")
        return True

    log_run(db, run.id, SyncLogLevel.info, f"{code.value} completed status={job.status.value}")
    return True


def _fail_remaining_provider_stages(
    db: Session,
    tracker: SyncProgressTracker,
    provider_code: str,
    message: str,
) -> None:
    run = db.get(SyncRun, tracker.run_id)
    progress = run.progress if run else None
    for phase in ("dictionaries", "free", "purchased"):
        sid = stage_for_provider_phase(provider_code, phase)
        if not sid:
            continue
        st = stage_status(progress, sid)
        if st not in {"pending", "running"}:
            continue
        # Pending stages never ran — don't imply they called the failing endpoint.
        detail = (
            f"skipped after {provider_code} failed: {message}"
            if st == "pending"
            else message
        )
        tracker.fail(sid, detail)


async def _run_operator_enrichment(
    db: Session,
    *,
    run: SyncRun,
    tracker: SyncProgressTracker,
    category_stats: dict[str, Any],
    only_missing: bool = False,
) -> None:
    tracker.begin("operator_enrichment", "Обогащение PSTN")
    provider = db.scalars(
        select(Provider)
        .options(joinedload(Provider.connection))
        .where(Provider.code == ProviderCode.finenumbers)
    ).first()
    if provider is None or provider.connection is None:
        tracker.fail("operator_enrichment", "Finenumbers connection missing")
        return

    conn_row = provider.connection
    connection = ConnectionConfig(
        base_url=conn_row.base_url,
        auth_settings=dict(conn_row.auth_settings or {}),
        extra_settings=dict(conn_row.extra_settings or {}),
    )
    def _on_enrich_progress(detail: str, current: int | None, total: int | None) -> None:
        tracker.progress(
            "operator_enrichment",
            detail=detail,
            substage=detail,
            current=current,
            total=total,
            unit="numbers",
        )

    try:
        # Last sync stage: fill operator on every present free/purchased row (only_missing=False).
        enrich_stats = await enrich_catalog_operators(
            db,
            connection=connection,
            on_progress=_on_enrich_progress,
            only_missing=only_missing,
        )
        category_stats["operator_enrichment"] = enrich_stats
        log_run(
            db,
            run.id,
            SyncLogLevel.info,
            (
                "Operator enrichment "
                f"updated={enrich_stats.get('updated')} "
                f"lookups={enrich_stats.get('lookups')} "
                f"cache_hits={enrich_stats.get('cache_hits')}"
            ),
            enrich_stats,
        )
        tracker.end(
            "operator_enrichment",
            f"updated={enrich_stats.get('updated')}, lookups={enrich_stats.get('lookups')}, "
            f"cache_hits={enrich_stats.get('cache_hits')}",
        )
    except ProviderError as exc:
        if isinstance(exc.details, dict) and exc.details:
            category_stats["operator_enrichment"] = dict(exc.details)
        log_run(
            db,
            run.id,
            SyncLogLevel.error,
            f"Operator enrichment failed: {exc}",
            {"code": exc.code, "details": exc.details or {}},
        )
        tracker.fail("operator_enrichment", str(exc))
    except Exception as exc:
        log_run(db, run.id, SyncLogLevel.error, f"Operator enrichment failed: {exc}")
        tracker.fail("operator_enrichment", str(exc))
