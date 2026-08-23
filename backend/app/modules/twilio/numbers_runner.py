"""Per-row Twilio number enrichment — isolated from the RU catalog."""

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
from app.modules.sync_engine.locks import advisory_unlock_conn, try_advisory_lock_conn
from app.modules.twilio.cells import NumberCell, build_number_cells, should_repeat_contains
from app.modules.twilio.persist import (
    catalog_has_rows,
    cutover_numbers_row,
    get_catalog_row,
    ingest_available_batch,
    load_geo_rows,
    mark_numbers_synced,
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
    twilio_connection_config,
)
from app.providers.errors import ProviderError
from app.providers.twilio import contract
from app.providers.twilio.client import TwilioClient

logger = logging.getLogger(__name__)


def _numbers_progress(country_iso: str, number_type: str) -> dict[str, Any]:
    return {
        "current_stage_id": "numbers",
        "target": {"country_iso": country_iso, "number_type": number_type},
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
    country_iso: str,
    number_type: str,
    triggered_by: str = "api",
) -> SyncJob:
    provider = get_twilio_provider(db)
    if not catalog_has_rows(db, provider_id=provider.id):
        raise ProviderError("Сначала выполните «Загрузка регионов»")
    if get_active_twilio_job(db):
        raise ProviderError("Синхронизация Twilio уже выполняется")
    iso = country_iso.strip().upper()
    ntype = number_type.strip()
    if ntype not in contract.SEARCH_TYPE_PATHS:
        raise ProviderError(f"Неизвестный тип Twilio: {ntype}")
    row = get_catalog_row(db, provider_id=provider.id, country_iso=iso, number_type=ntype)
    if row is None:
        raise ProviderError("Нет строки покрытия для этой страны и типа")
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
) -> str:
    parts = [f"{pattern_index} / {repeat} / {cell_index} / {cell_total}"]
    if cell.region_filter:
        parts.append(cell.region_filter)
    elif cell.label:
        parts.append(cell.label)
    if contains:
        parts.append(contains)
    parts.append(f"{returned} номеров")
    return " · ".join(parts)


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


async def _execute_numbers(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    lock_conn = None
    client: TwilioClient | None = None
    lock_gate = threading.Lock()
    stop_keepalive = asyncio.Event()
    keepalive_task: asyncio.Task[None] | None = None
    try:
        lock_conn = lock_engine.connect()
        if not try_advisory_lock_conn(lock_conn, TWILIO_LOCK_KEY):
            job = db.get(SyncJob, job_id)
            if job:
                job.status = SyncJobStatus.failed
                job.error_summary = "Синхронизация Twilio уже выполняется (lock)"
                job.finished_at = _now()
                db.commit()
            return

        job = db.get(SyncJob, job_id)
        if job is None:
            return
        progress = (job.stats or {}).get("progress") or {}
        target = progress.get("target") or {}
        country_iso = str(target.get("country_iso") or "").strip().upper()
        number_type = str(target.get("number_type") or "").strip()
        provider = get_twilio_provider(db)
        catalog = get_catalog_row(
            db,
            provider_id=provider.id,
            country_iso=country_iso,
            number_type=number_type,
        )
        if catalog is None:
            job.status = SyncJobStatus.failed
            job.error_summary = "Строка покрытия исчезла"
            job.finished_at = _now()
            db.commit()
            return

        job.status = SyncJobStatus.running
        job.started_at = _now()
        db.commit()

        _ping_lock_gated(lock_conn, lock_gate)
        keepalive_task = asyncio.create_task(
            _lock_keepalive(lock_conn, lock_gate, stop_keepalive),
            name=f"twilio-numbers-lock-{job_id}",
        )
        client = TwilioClient(twilio_connection_config(provider))
        tracker = _Progress(db, job)
        geo_rows = load_geo_rows(
            db,
            provider_id=provider.id,
            country_iso=country_iso,
            number_type=number_type,
        )
        cells = build_number_cells(geo_rows)
        tracker.requests_total = len(cells)
        row_view = _row_view(
            country_iso=country_iso,
            country_name=catalog.country_name,
            number_type=number_type,
            status="running",
            detail=f"0 / 1 / 1 / {len(cells)}",
            number_count=0,
            region_count=catalog.region_count,
            city_count=catalog.city_count,
            period_price=catalog.period_price,
            price_unit=catalog.price_unit,
        )
        tracker.apply(rows=[row_view], force=True, stage_id="numbers", stage_status="running")

        def _commit_batch(
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
                provider_id=provider.id,
                job_id=job.id,
                country_iso=country_iso,
                country_name=catalog.country_name,
                number_type=number_type,
                region_filter=cell.region_filter,
                items=batch,
                source=contract.NUMBER_SOURCE_NUMBERS,
            )
            tracker.note_batch(country_iso, number_type, result)
            row_view["status"] = "running"
            row_view["detail"] = _numbers_detail(
                pattern_index,
                repeat,
                cell_index,
                len(cells),
                cell,
                contains,
                len(batch),
            )
            row_view["number_count"] = tracker.row_number_count(country_iso, number_type)
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

        for cell_index, cell in enumerate(cells, start=1):
            in_region = cell.region_filter or None
            in_locality = cell.locality
            first = await _search_or_empty(
                client,
                country_iso=country_iso,
                number_type=number_type,
                in_region=in_region,
                in_locality=in_locality,
            )
            tracker.bump_request()
            _commit_batch(
                batch=first,
                cell=cell,
                cell_index=cell_index,
                pattern_index=0,
                repeat=1,
                contains=None,
            )
            patterns = contract.geo_contains_queue(len(first))
            if not patterns:
                continue
            tracker.requests_total = (tracker.requests_total or 0) + len(patterns)
            for pattern_index, pattern in enumerate(patterns, start=1):
                seen: set[str] = set()
                repeat = 0
                while True:
                    repeat += 1
                    batch = await _search_or_empty(
                        client,
                        country_iso=country_iso,
                        number_type=number_type,
                        in_region=in_region,
                        in_locality=in_locality,
                        contains=pattern,
                    )
                    tracker.bump_request()
                    phones = {
                        str(item.get("phone_number") or "").strip()
                        for item in batch
                        if str(item.get("phone_number") or "").strip()
                    }
                    new_unique = len(phones - seen)
                    seen.update(phones)
                    _commit_batch(
                        batch=batch,
                        cell=cell,
                        cell_index=cell_index,
                        pattern_index=pattern_index,
                        repeat=repeat,
                        contains=pattern,
                    )
                    if not should_repeat_contains(len(batch), new_unique):
                        break

        wipe = cutover_numbers_row(
            db,
            provider_id=provider.id,
            job_id=job.id,
            country_iso=country_iso,
            number_type=number_type,
        )
        mark_numbers_synced(
            db,
            provider_id=provider.id,
            country_iso=country_iso,
            number_type=number_type,
            job_id=job.id,
            geo_job_id=catalog.last_sync_job_id,
        )
        row_view["status"] = "success"
        row_view["detail"] = ""
        row_view["number_count"] = tracker.row_number_count(country_iso, number_type)
        tracker.requests_total = tracker.requests
        tracker.apply(
            rows=[row_view],
            force=True,
            stage_id="numbers",
            stage_status="success",
            stage_detail=f"{row_view['number_count']} номеров",
        )
        job.status = SyncJobStatus.success
        job.finished_at = _now()
        stats = dict(job.stats or {})
        stats["counts"] = {
            "requests": tracker.requests,
            "numbers_unique": tracker.row_number_count(country_iso, number_type),
            "numbers_deleted": wipe,
            "cells": len(cells),
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
        if lock_conn is not None:
            try:
                advisory_unlock_conn(lock_conn, TWILIO_LOCK_KEY)
            except Exception:
                logger.exception("Failed to unlock Twilio lock")
            try:
                lock_conn.close()
            except Exception:
                logger.exception("Failed to close Twilio lock connection")
        try:
            db.close()
        except Exception:
            logger.exception("Failed to close Twilio numbers db session")
