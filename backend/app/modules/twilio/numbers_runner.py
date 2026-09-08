"""Twilio number enrichment — per row or a chained pass over the catalog."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal, lock_engine
from app.models.enums import SyncJobStatus, SyncJobType
from app.models.sync import SyncJob
from app.models.twilio import TwilioCatalog
from app.modules.sync_engine.locks import advisory_unlock_conn, try_advisory_lock_conn
from app.modules.twilio.cells import (
    NumberCell,
    apply_batch_novelty,
    enrich_cells,
    should_repeat_pattern,
)
from app.modules.twilio.persist import (
    adopt_row_ingest,
    catalog_has_rows,
    catalog_numbers_loaded,
    cutover_numbers_row,
    empty_numbers_checkpoint,
    get_catalog_row,
    finalize_coverage_geo,
    ingest_available_batch,
    list_catalog_rows,
    load_row_known,
    mark_numbers_synced,
    number_count_for_row,
    realign_available_number_iso,
    refresh_local_counts,
    save_catalog_numbers_state,
)
from app.modules.twilio.runner import (
    TWILIO_LOCK_KEY,
    _Progress,
    _lock_keepalive,
    _now,
    _ping_lock_gated,
    _search_or_empty,
    get_active_twilio_job,
    get_twilio_provider,
    reclaim_stale_twilio_jobs,
    touch_job_heartbeat,
    twilio_connection_config,
)
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.twilio import contract
from app.providers.twilio.client import TwilioClient

logger = logging.getLogger(__name__)


def numbers_job_outcome(row_errors: int, row_count: int) -> SyncJobStatus:
    if row_count > 0 and row_errors == row_count:
        return SyncJobStatus.failed
    return SyncJobStatus.success


def _numbers_progress(
    country_iso: str | None = None,
    number_type: str | None = None,
) -> dict[str, Any]:
    return {
        "current_stage_id": "numbers",
        "target": {"country_iso": country_iso, "number_type": number_type},
        "mode": "all" if not country_iso else "row",
        "stages": [
            {
                "id": "numbers",
                "group": "Twilio",
                "label": "Номера",
                "status": "pending",
                "detail": "",
                "started_at": None,
                "finished_at": None,
            }
        ],
        "summary": {"requests": 0, "requests_total": None, "cities_total": 0, "numbers_unique": 0},
        "current": {"country_iso": country_iso, "in_region": None, "contains": None},
        "rows": [],
    }


def create_twilio_numbers_job(
    db: Session,
    *,
    country_iso: str | None = None,
    number_type: str | None = None,
    triggered_by: str = "api",
) -> SyncJob:
    provider = get_twilio_provider(db)
    reclaim_stale_twilio_jobs(db)
    if not catalog_has_rows(db, provider_id=provider.id):
        raise ProviderError("Сначала выполните «Загрузка стран»")
    if get_active_twilio_job(db):
        raise ProviderError("Синхронизация Twilio уже выполняется")
    iso = (country_iso or "").strip().upper() or None
    ntype = (number_type or "").strip() or None
    if bool(iso) != bool(ntype):
        raise ProviderError("Укажите и страну, и тип — или оставьте оба поля пустыми")
    if ntype and ntype not in contract.SEARCH_TYPE_PATHS:
        raise ProviderError(f"Неизвестный тип Twilio: {ntype}")
    if iso and ntype:
        row = get_catalog_row(db, provider_id=provider.id, country_iso=iso, number_type=ntype)
        if row is None:
            raise ProviderError("Нет строки покрытия для этой страны и типа")
        if not catalog_numbers_loaded(row):
            existing = find_resumable_numbers_job(db, country_iso=iso, number_type=ntype)
            if existing is not None:
                if existing.status in (SyncJobStatus.pending, SyncJobStatus.running):
                    raise ProviderError("Синхронизация Twilio уже выполняется")
                _reopen_numbers_job(existing)
                db.commit()
                db.refresh(existing)
                return existing
    job = SyncJob(
        provider_id=provider.id,
        job_type=SyncJobType.twilio_numbers,
        status=SyncJobStatus.pending,
        triggered_by=triggered_by,
        stats={"progress": _numbers_progress(iso, ntype)},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_latest_twilio_numbers_job(db: Session) -> SyncJob | None:
    return db.scalar(
        select(SyncJob)
        .where(SyncJob.job_type == SyncJobType.twilio_numbers)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )


def spawn_twilio_numbers_job(job_id: uuid.UUID) -> None:
    def _runner() -> None:
        try:
            asyncio.run(_execute_numbers(job_id))
        except Exception:
            logger.exception("Twilio numbers thread crashed job_id=%s", job_id)

    threading.Thread(target=_runner, name=f"twilio-numbers-{job_id}", daemon=True).start()


def _numbers_detail(
    pattern_index: int,
    repeat: int,
    cell_index: int,
    cell_total: int,
    cell: NumberCell,
    contains: str | None,
    returned: int,
    requests: int | None = None,
) -> str:
    del returned
    label = cell.region_filter or cell.label or "—"
    parts = [f"штат {cell_index}/{cell_total}", label]
    if contains:
        parts.append(contains)
    elif pattern_index == 0:
        parts.append("probe")
    parts.append(f"повтор {repeat}")
    if requests is not None:
        parts.append(f"запросы {requests}")
    return " · ".join(parts)


def _checkpoint_from_catalog(catalog: TwilioCatalog) -> dict[str, Any]:
    raw = catalog.numbers_checkpoint
    if not isinstance(raw, dict):
        return empty_numbers_checkpoint()
    completed = raw.get("completed_cells") or []
    if not isinstance(completed, list):
        completed = []
    return {
        "completed_cells": [str(item).strip().upper() for item in completed if str(item).strip()],
        "current_cell": str(raw.get("current_cell") or "").strip().upper() or None,
        "last_completed_pattern_index": int(raw.get("last_completed_pattern_index") or 0),
    }


def _cell_key(cell: NumberCell) -> str:
    return (cell.region_filter or "").strip().upper()


def find_resumable_numbers_job(
    db: Session,
    *,
    country_iso: str | None,
    number_type: str | None,
) -> SyncJob | None:
    jobs = list(
        db.scalars(
            select(SyncJob)
            .where(SyncJob.job_type == SyncJobType.twilio_numbers)
            .order_by(SyncJob.created_at.desc())
        ).all()
    )
    iso = (country_iso or "").strip().upper() or None
    ntype = (number_type or "").strip() or None
    for job in jobs:
        progress = (job.stats or {}).get("progress") or {}
        target = progress.get("target") or {}
        job_iso = str(target.get("country_iso") or "").strip().upper() or None
        job_type = str(target.get("number_type") or "").strip() or None
        if iso and (job_iso != iso or job_type != ntype):
            continue
        if job.status in (SyncJobStatus.pending, SyncJobStatus.running):
            return job
        if job.status == SyncJobStatus.failed:
            return job
        return None
    return None


def _reopen_numbers_job(job: SyncJob) -> None:
    job.status = SyncJobStatus.pending
    job.finished_at = None
    job.error_summary = None
    touch_job_heartbeat(job)


def _row_view(
    *,
    country_iso: str,
    country_name: str | None,
    number_type: str,
    status: str,
    detail: str,
    number_count: int,
    region_count: int = 0,
    city_count: int = 0,
    period_price: Any = None,
    price_unit: str | None = None,
) -> dict[str, Any]:
    return {
        "country_iso": country_iso,
        "country_name": country_name,
        "number_type": number_type,
        "status": status,
        "detail": detail,
        "region_count": region_count,
        "city_count": city_count,
        "number_count": number_count,
        "period_price": str(period_price) if period_price is not None else None,
        "price_unit": price_unit,
    }


async def _enrich_catalog_row(
    *,
    client: TwilioClient,
    db: Session,
    tracker: _Progress,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    catalog: TwilioCatalog,
) -> dict[str, Any]:
    country_iso = (catalog.country_iso or "").strip().upper()
    number_type = (catalog.number_type or "").strip()
    cells = enrich_cells(country_iso, number_type)
    adopt_row_ingest(
        db,
        provider_id=provider_id,
        country_iso=country_iso,
        number_type=number_type,
        job_id=job_id,
    )
    known_phones, known_regions, known_cities = load_row_known(
        db,
        provider_id=provider_id,
        country_iso=country_iso,
        number_type=number_type,
    )
    checkpoint = _checkpoint_from_catalog(catalog)
    completed_cells = set(checkpoint["completed_cells"])
    current_cell = checkpoint["current_cell"]
    last_completed_pattern_index = int(checkpoint["last_completed_pattern_index"] or 0)
    patterns = contract.contains_region_patterns()
    extra_repeats = max(0, tracker.requests - (len(completed_cells) * (1 + len(patterns))))
    tracker.requests_total = len(cells) * (1 + len(patterns)) + extra_repeats
    save_catalog_numbers_state(
        db,
        provider_id=provider_id,
        country_iso=country_iso,
        number_type=number_type,
        last_error=None,
        clear_error=True,
        heartbeat=True,
    )
    row_view = _row_view(
        country_iso=country_iso,
        country_name=catalog.country_name,
        number_type=number_type,
        status="running",
        detail=f"штат 0/{len(cells)}",
        number_count=len(known_phones),
        region_count=len(known_regions),
        city_count=len(known_cities),
        period_price=catalog.period_price,
        price_unit=catalog.price_unit,
    )
    progress = (tracker.job.stats or {}).get("progress") or {}
    progress["target"] = {"country_iso": country_iso, "number_type": number_type}
    tracker.apply(rows=[row_view], force=True, stage_id="numbers", stage_status="running")

    def _persist_checkpoint(*, cell: NumberCell, pattern_index: int, cell_done: bool) -> None:
        key = _cell_key(cell)
        if cell_done:
            completed_cells.add(key)
            checkpoint["current_cell"] = None
            checkpoint["last_completed_pattern_index"] = 0
        else:
            checkpoint["current_cell"] = key
            checkpoint["last_completed_pattern_index"] = pattern_index
        checkpoint["completed_cells"] = sorted(completed_cells)
        save_catalog_numbers_state(
            db,
            provider_id=provider_id,
            country_iso=country_iso,
            number_type=number_type,
            checkpoint=checkpoint,
            heartbeat=True,
        )

    async def _commit_batch(
        *,
        batch: list[dict[str, Any]],
        cell: NumberCell,
        cell_index: int,
        pattern_index: int,
        repeat: int,
        contains: str | None,
    ) -> None:
        result = ingest_available_batch(
            db,
            provider_id=provider_id,
            job_id=job_id,
            country_iso=country_iso,
            country_name=catalog.country_name,
            number_type=number_type,
            region_filter=cell.region_filter,
            items=batch,
            source=contract.NUMBER_SOURCE_NUMBERS,
        )
        tracker.note_batch(country_iso, number_type, result)
        row_view["region_count"] = len(known_regions)
        row_view["city_count"] = len(known_cities)
        row_view["number_count"] = len(known_phones)
        row_view["status"] = "running"
        row_view["detail"] = _numbers_detail(
            pattern_index,
            repeat,
            cell_index,
            len(cells),
            cell,
            contains,
            len(batch),
            requests=tracker.requests,
        )
        tracker.apply(
            current={
                "country_iso": country_iso,
                "in_region": cell.region_filter or None,
                "contains": contains,
            },
            rows=[row_view],
            stage_id="numbers",
            stage_status="running",
            stage_detail=row_view["detail"],
        )
        save_catalog_numbers_state(
            db,
            provider_id=provider_id,
            country_iso=country_iso,
            number_type=number_type,
            heartbeat=True,
        )

    for cell_index, cell in enumerate(cells, start=1):
        key = _cell_key(cell)
        if key in completed_cells:
            continue
        in_region = cell.region_filter or None
        resume_this = current_cell == key and last_completed_pattern_index > 0
        if not resume_this:
            first = await _search_or_empty(
                client,
                country_iso=country_iso,
                number_type=number_type,
                in_region=in_region,
                strict=True,
            )
            tracker.bump_request()
            apply_batch_novelty(first, known_phones, known_regions, known_cities)
            await _commit_batch(
                batch=first,
                cell=cell,
                cell_index=cell_index,
                pattern_index=0,
                repeat=1,
                contains=None,
            )
            if not first:
                _persist_checkpoint(cell=cell, pattern_index=0, cell_done=True)
                continue
            start_pattern = 1
        else:
            start_pattern = last_completed_pattern_index + 1
        for pattern_index, pattern in enumerate(patterns, start=1):
            if pattern_index < start_pattern:
                continue
            streak = 0
            repeat = 0
            while True:
                repeat += 1
                if repeat > 1:
                    tracker.requests_total = (tracker.requests_total or 0) + 1
                batch = await _search_or_empty(
                    client,
                    country_iso=country_iso,
                    number_type=number_type,
                    in_region=in_region,
                    contains=pattern,
                    strict=True,
                )
                tracker.bump_request()
                new_facts = apply_batch_novelty(batch, known_phones, known_regions, known_cities)
                if new_facts:
                    streak = 0
                else:
                    streak += 1
                await _commit_batch(
                    batch=batch,
                    cell=cell,
                    cell_index=cell_index,
                    pattern_index=pattern_index,
                    repeat=repeat,
                    contains=pattern,
                )
                if not should_repeat_pattern(len(batch), streak):
                    break
            _persist_checkpoint(cell=cell, pattern_index=pattern_index, cell_done=False)
        region_count, city_count = refresh_local_counts(
            db,
            provider_id=provider_id,
            country_iso=country_iso,
            number_type=number_type,
        )
        row_view["region_count"] = region_count
        row_view["city_count"] = city_count
        _persist_checkpoint(cell=cell, pattern_index=len(patterns), cell_done=True)

    cutover_numbers_row(
        db,
        provider_id=provider_id,
        job_id=job_id,
        country_iso=country_iso,
        number_type=number_type,
    )
    mark_numbers_synced(
        db,
        provider_id=provider_id,
        country_iso=country_iso,
        number_type=number_type,
        job_id=job_id,
        geo_job_id=catalog.last_sync_job_id,
    )
    region_count, city_count = finalize_coverage_geo(
        db,
        provider_id=provider_id,
        country_iso=country_iso,
        number_type=number_type,
        job_id=job_id,
    )
    row_view["status"] = "success"
    row_view["detail"] = ""
    row_view["region_count"] = region_count
    row_view["city_count"] = city_count
    row_view["number_count"] = number_count_for_row(
        db, provider_id=provider_id, country_iso=country_iso, number_type=number_type
    )
    tracker.apply(
        rows=[row_view],
        force=True,
        stage_id="numbers",
        stage_status="running",
        stage_detail=f"{row_view['number_count']} номеров",
    )
    db.commit()
    return row_view


async def _execute_numbers(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    lock_conn = None
    client: TwilioClient | None = None
    lock_gate = threading.Lock()
    lock_box: dict[str, Any] = {"conn": None, "gate": lock_gate}
    stop_keepalive = asyncio.Event()
    keepalive_task: asyncio.Task[None] | None = None
    try:
        lock_conn = lock_engine.connect()
        lock_box["conn"] = lock_conn
        if not try_advisory_lock_conn(lock_conn, TWILIO_LOCK_KEY):
            job = db.get(SyncJob, job_id)
            if job and job.status == SyncJobStatus.pending:
                job.status = SyncJobStatus.failed
                job.error_summary = "Синхронизация Twilio уже выполняется (lock)"
                job.finished_at = _now()
                db.commit()
            return

        job = db.get(SyncJob, job_id)
        if job is None or job.status != SyncJobStatus.pending:
            return
        progress = (job.stats or {}).get("progress") or {}
        target = progress.get("target") or {}
        country_iso = str(target.get("country_iso") or "").strip().upper() or None
        number_type = str(target.get("number_type") or "").strip() or None
        provider = get_twilio_provider(db)
        if country_iso and number_type:
            rows = []
            one = get_catalog_row(
                db,
                provider_id=provider.id,
                country_iso=country_iso,
                number_type=number_type,
            )
            if one is None:
                job.status = SyncJobStatus.failed
                job.error_summary = "Строка покрытия исчезла"
                job.finished_at = _now()
                db.commit()
                return
            rows = [one]
        else:
            rows = list_catalog_rows(db, provider_id=provider.id)
            if not rows:
                job.status = SyncJobStatus.failed
                job.error_summary = "Сначала выполните «Загрузка стран»"
                job.finished_at = _now()
                db.commit()
                return

        job.status = SyncJobStatus.running
        job.started_at = _now()
        db.commit()

        _ping_lock_gated(lock_conn, lock_gate)
        keepalive_task = asyncio.create_task(
            _lock_keepalive(lock_box, stop_keepalive),
            name=f"twilio-numbers-lock-{job_id}",
        )
        client = TwilioClient(twilio_connection_config(provider))
        realign_available_number_iso(db, provider_id=provider.id)
        db.commit()
        tracker = _Progress(db, job)
        row_errors = 0
        last_view: dict[str, Any] | None = None
        for catalog in rows:
            catalog = db.merge(catalog)
            try:
                last_view = await _enrich_catalog_row(
                    client=client,
                    db=db,
                    tracker=tracker,
                    provider_id=provider.id,
                    job_id=job.id,
                    catalog=catalog,
                )
            except ProviderAuthError:
                raise
            except Exception as exc:
                logger.exception(
                    "Twilio numbers row failed %s %s",
                    catalog.country_iso,
                    catalog.number_type,
                )
                try:
                    db.rollback()
                except Exception:
                    logger.exception("Failed to rollback after Twilio numbers row error")
                row_errors += 1
                save_catalog_numbers_state(
                    db,
                    provider_id=provider.id,
                    country_iso=(catalog.country_iso or "").strip().upper(),
                    number_type=(catalog.number_type or "").strip(),
                    last_error=str(exc)[:500],
                    heartbeat=True,
                )
                failed = _row_view(
                    country_iso=(catalog.country_iso or "").strip().upper(),
                    country_name=catalog.country_name,
                    number_type=(catalog.number_type or "").strip(),
                    status="failed",
                    detail=str(exc)[:300],
                    number_count=number_count_for_row(
                        db,
                        provider_id=provider.id,
                        country_iso=(catalog.country_iso or "").strip().upper(),
                        number_type=(catalog.number_type or "").strip(),
                    ),
                    region_count=catalog.region_count,
                    city_count=catalog.city_count,
                    period_price=catalog.period_price,
                    price_unit=catalog.price_unit,
                )
                last_view = failed
                tracker.apply(
                    rows=[failed],
                    force=True,
                    stage_id="numbers",
                    stage_status="running",
                    stage_detail=failed["detail"],
                )

        if last_view is not None and last_view.get("status") != "failed":
            last_view["status"] = "success"
            last_view["detail"] = ""
        outcome = numbers_job_outcome(row_errors, len(rows))
        tracker.requests_total = tracker.requests
        tracker.apply(
            rows=[last_view] if last_view else [],
            force=True,
            stage_id="numbers",
            stage_status=outcome.value,
            stage_detail=f"{tracker.requests} запросов",
        )
        job.status = outcome
        if outcome == SyncJobStatus.failed:
            job.error_summary = f"Не удалось загрузить номера: {row_errors} из {len(rows)} строк"
        job.finished_at = _now()
        stats = dict(job.stats or {})
        stats["counts"] = {
            "requests": tracker.requests,
            "rows": len(rows),
            "row_errors": row_errors,
        }
        job.stats = stats
        flag_modified(job, "stats")
        db.commit()
    except Exception as exc:
        logger.exception("Twilio numbers sync failed")
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job:
            job.status = SyncJobStatus.failed
            job.error_summary = str(exc)
            job.finished_at = _now()
            db.commit()
    finally:
        stop_keepalive.set()
        if keepalive_task is not None:
            try:
                await keepalive_task
            except Exception:
                logger.exception("Twilio numbers keepalive failed on shutdown")
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.exception("Failed to close Twilio client")
        held = lock_box.get("conn") or lock_conn
        if held is not None:
            try:
                advisory_unlock_conn(held, TWILIO_LOCK_KEY)
            except Exception:
                logger.exception("Failed to unlock Twilio lock")
            try:
                held.close()
            except Exception:
                logger.exception("Failed to close Twilio lock connection")
        try:
            db.close()
        except Exception:
            logger.exception("Failed to close Twilio numbers db session")


def _boot_resumable_numbers_job(db: Session) -> SyncJob | None:
    job = get_latest_twilio_numbers_job(db)
    if job is None or job.status != SyncJobStatus.failed:
        return None
    summary = (job.error_summary or "").lower()
    if "auth" in summary or "twilio_auth" in summary:
        return None
    progress = (job.stats or {}).get("progress") or {}
    target = progress.get("target") or {}
    iso = str(target.get("country_iso") or "").strip().upper()
    ntype = str(target.get("number_type") or "").strip()
    if not iso or not ntype:
        return None
    provider = get_twilio_provider(db)
    row = get_catalog_row(db, provider_id=provider.id, country_iso=iso, number_type=ntype)
    if row is None or catalog_numbers_loaded(row):
        return None
    return job


def respawn_interrupted_twilio_on_boot() -> None:
    from app.modules.twilio.runner import list_active_twilio_jobs, spawn_twilio_job, twilio_lock_is_free

    db = SessionLocal()
    try:
        active = list_active_twilio_jobs(db)
        for job in active:
            touch_job_heartbeat(job)
        if active:
            db.commit()
        if not twilio_lock_is_free():
            return
        job = get_active_twilio_job(db)
        if job is None:
            job = _boot_resumable_numbers_job(db)
            if job is None:
                return
        _reopen_numbers_job(job)
        db.commit()
        if job.job_type == SyncJobType.twilio_numbers:
            spawn_twilio_numbers_job(job.id)
        else:
            spawn_twilio_job(job.id)
        logger.info("Respawned interrupted Twilio job_id=%s type=%s", job.id, job.job_type)
    except Exception:
        logger.exception("Failed to respawn interrupted Twilio job")
        try:
            db.rollback()
        except Exception:
            logger.exception("Failed to rollback after Twilio boot respawn error")
    finally:
        db.close()
