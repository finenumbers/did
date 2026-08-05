"""Unified multi-provider sync with stage progress for the Sync UI."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.db import SessionLocal
from app.models.enums import ProviderCode, SyncJobStatus, SyncJobType, SyncLogLevel
from app.models.providers import Provider
from app.models.sync import SyncJob, SyncRun
from app.modules.sync_engine.dropped_export import (
    begin_dropped_export,
    end_dropped_export,
    get_collector,
    write_dropped_xlsx,
)
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.progress import (
    SyncProgressTracker,
    build_initial_progress,
    stage_for_provider_phase,
    stage_status,
)
from app.modules.sync_engine.run_file_log import begin_sync_debug_log, end_sync_debug_log
from app.modules.sync_engine.run_logging import log_run
from app.modules.sync_engine.safety import build_inventory_summary
from app.modules.sync_engine.service import SyncService
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderCapabilityLimitedError, ProviderError
from app.providers.finenumbers.enrich import enrich_catalog_operators
from app.providers.registry import get_provider

logger = logging.getLogger(__name__)

STALE_RUNNING_MINUTES = 180
STALE_PENDING_MINUTES = 30
PROVIDER_ORDER = (
    ProviderCode.sipout,
    ProviderCode.runexis,
    ProviderCode.uis,
    ProviderCode.aurora,
    ProviderCode.finenumbers,
)
ACTIVE_STATUSES = (SyncJobStatus.pending, SyncJobStatus.running)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mark_stale_runs(db: Session) -> int:
    cutoff_running = _now() - timedelta(minutes=STALE_RUNNING_MINUTES)
    cutoff_pending = _now() - timedelta(minutes=STALE_PENDING_MINUTES)
    running = db.scalars(
        select(SyncRun).where(
            SyncRun.status == SyncJobStatus.running,
            SyncRun.started_at.is_not(None),
            SyncRun.started_at < cutoff_running,
        )
    ).all()
    pending = db.scalars(
        select(SyncRun).where(
            SyncRun.status == SyncJobStatus.pending,
            SyncRun.created_at < cutoff_pending,
        )
    ).all()
    rows = list(running) + list(pending)
    for run in rows:
        run.status = SyncJobStatus.failed
        if run.started_at is not None:
            run.error_summary = (
                f"Marked stale: running longer than {STALE_RUNNING_MINUTES} minutes"
            )
        else:
            run.error_summary = (
                f"Marked stale: pending longer than {STALE_PENDING_MINUTES} minutes"
            )
        run.finished_at = _now()
        log_run(db, run.id, SyncLogLevel.error, run.error_summary)
    if rows:
        db.commit()
    return len(rows)


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
            run.status = SyncJobStatus.failed
            run.error_summary = "Marked orphan: running but sync lock was free"
            run.finished_at = _now()
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


async def execute_unified_run(run_id: uuid.UUID) -> None:
    from app.modules.sync_engine.locks import SYNC_LOCK_KEY, advisory_unlock, try_advisory_lock
    from app.modules.sync_engine.scheduler import _set_last_fired_date
    from zoneinfo import ZoneInfo

    db = SessionLocal()
    locked = False
    try:
        if not try_advisory_lock(db, SYNC_LOCK_KEY):
            run = db.get(SyncRun, run_id)
            if run is not None and run.status in ACTIVE_STATUSES:
                run.status = SyncJobStatus.failed
                run.error_summary = "Синхронизация уже выполняется (lock)"
                run.finished_at = _now()
                db.commit()
            return
        locked = True
        db.commit()
        run = db.get(SyncRun, run_id)
        if run is not None and (run.triggered_by or "") == "schedule":
            day_key = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
            try:
                _set_last_fired_date(db, day_key)
            except Exception:
                logger.exception(
                    "Failed to mark schedule last_fired for run_id=%s; aborting run",
                    run_id,
                )
                run.status = SyncJobStatus.failed
                run.error_summary = "Failed to mark schedule last_fired"
                run.finished_at = _now()
                db.commit()
                return
        await _execute_unified_run(db, run_id)
    except Exception:
        logger.exception("Unified sync crashed run_id=%s", run_id)
        try:
            db.rollback()
            run = db.get(SyncRun, run_id)
            if run is not None:
                run.status = SyncJobStatus.failed
                run.error_summary = "Unexpected sync failure"
                run.finished_at = _now()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        if locked:
            try:
                advisory_unlock(db, SYNC_LOCK_KEY)
            except Exception:
                pass
        db.close()


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

        for code in PROVIDER_ORDER:
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
            ok = await _sync_provider(
                db,
                run=run,
                tracker=tracker,
                provider=provider,
                category_stats=category_stats,
            )
            if ok:
                provider_ok += 1
            else:
                provider_failures.append(code.value)

        await _run_operator_enrichment(
            db, run=run, tracker=tracker, category_stats=category_stats
        )

        tracker.begin("finalize", "Завершение")
        try:
            dropped_meta = write_dropped_xlsx()
            dropped_written = True
        except Exception:
            logger.exception("Failed to write sync dropped XLSX")
            dropped_meta = {"available": False, "error": "write_failed"}

        inventory_summary = build_inventory_summary(category_stats)
        summary = {
            "providers_ok": provider_ok,
            "providers_failed": provider_failures,
            "categories": category_stats,
            "inventory_summary": inventory_summary,
            "dropped_export": dropped_meta,
        }
        run.stats = summary
        db.commit()
        tracker.end(
            "finalize",
            f"ok={provider_ok}, failed={len(provider_failures)}",
        )

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
) -> bool:
    code = provider.code
    adapter = get_provider(code)
    caps = adapter.capabilities()

    if code != ProviderCode.finenumbers and not caps.get("purchased_numbers", {}).get("supported"):
        stage = stage_for_provider_phase(code.value, "purchased")
        if stage:
            tracker.skip(stage, "capability not supported")

    if code in (ProviderCode.finenumbers, ProviderCode.aurora):
        mode = SyncMode.free_only
        job_type = SyncJobType.free_only
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
    except ProviderCapabilityLimitedError as exc:
        log_run(db, run.id, SyncLogLevel.error, f"{code.value}: capability limited: {exc}")
        _fail_remaining_provider_stages(db, tracker, code.value, str(exc))
        return False
    except Exception as exc:
        log_run(db, run.id, SyncLogLevel.error, f"{code.value}: {exc}")
        _fail_remaining_provider_stages(db, tracker, code.value, str(exc)[:400])
        return False

    db.refresh(run)
    category_stats[code.value] = (job.stats or {}).get("categories") or {}

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
        if st in {"pending", "running"}:
            tracker.fail(sid, message)


async def _run_operator_enrichment(
    db: Session,
    *,
    run: SyncRun,
    tracker: SyncProgressTracker,
    category_stats: dict[str, Any],
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
        enrich_stats = await enrich_catalog_operators(
            db,
            connection=connection,
            on_progress=_on_enrich_progress,
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
    except Exception as exc:
        log_run(db, run.id, SyncLogLevel.error, f"Operator enrichment failed: {exc}")
        tracker.fail("operator_enrichment", str(exc)[:400])
