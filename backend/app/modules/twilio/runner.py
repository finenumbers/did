"""Isolated Twilio coverage sync — not part of unified RU provider order / finalize stages."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal, lock_engine
from app.models.enums import ProviderCode, SyncJobStatus, SyncJobType
from app.models.providers import Provider
from app.models.sync import SyncJob
from app.modules.sync_engine.locks import advisory_unlock_conn, ping_lock_conn, try_advisory_lock_conn
from app.modules.twilio.persist import EmptyTwilioFetchError, persist_twilio_coverage
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError
from app.providers.twilio.client import TwilioClient
from app.providers.twilio.parser import build_catalog_rows

logger = logging.getLogger(__name__)

TWILIO_LOCK_KEY = 88221004
LOCK_KEEPALIVE_SECONDS = 30
PROGRESS_THROTTLE_SECONDS = 2.0

STAGES = (
    ("countries", "Страны"),
    ("pricing", "Цены"),
    ("cutover", "Запись каталога"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _progress_template() -> dict[str, Any]:
    return {
        "current_stage_id": None,
        "stages": [
            {
                "id": sid,
                "group": "Twilio",
                "label": label,
                "status": "pending",
                "detail": "",
                "started_at": None,
                "finished_at": None,
            }
            for sid, label in STAGES
        ],
    }


def _set_stage(job: SyncJob, stage_id: str, status: str, detail: str = "") -> None:
    stats = dict(job.stats or {})
    progress = stats.get("progress") or _progress_template()
    now = _now().isoformat()
    for stage in progress["stages"]:
        if stage["id"] == stage_id:
            stage["status"] = status
            stage["detail"] = detail
            if status == "running" and not stage.get("started_at"):
                stage["started_at"] = now
            if status in {"success", "failed", "skipped"}:
                stage["finished_at"] = now
    if status == "running":
        progress["current_stage_id"] = stage_id
    stats["progress"] = progress
    job.stats = stats
    flag_modified(job, "stats")


def _fail_current_stage(job: SyncJob, message: str) -> None:
    progress = (job.stats or {}).get("progress") or {}
    stage_id = progress.get("current_stage_id")
    if stage_id:
        _set_stage(job, str(stage_id), "failed", message[:500])


def _ping_lock_gated(lock_conn: Connection, gate: threading.Lock) -> None:
    with gate:
        ping_lock_conn(lock_conn)


async def _lock_keepalive(
    lock_conn: Connection,
    gate: threading.Lock,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=LOCK_KEEPALIVE_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await asyncio.to_thread(_ping_lock_gated, lock_conn, gate)
        except Exception:
            logger.exception("Twilio lock keepalive failed; lock session may be dead")
            return


def twilio_connection_config(provider: Provider) -> ConnectionConfig:
    conn = provider.connection
    if conn is None:
        raise ProviderError("Twilio connection settings missing")
    return ConnectionConfig(
        base_url=conn.base_url,
        auth_settings=dict(conn.auth_settings or {}),
        extra_settings=dict(conn.extra_settings or {}),
    )


def get_twilio_provider(db: Session) -> Provider:
    provider = db.scalar(
        select(Provider)
        .options(joinedload(Provider.connection))
        .where(Provider.code == ProviderCode.twilio)
    )
    if provider is None:
        raise ProviderError("Twilio provider is not seeded")
    return provider


def create_twilio_job(db: Session, *, triggered_by: str = "api") -> SyncJob:
    provider = get_twilio_provider(db)
    active = db.scalar(
        select(SyncJob).where(
            SyncJob.job_type == SyncJobType.twilio,
            SyncJob.status.in_((SyncJobStatus.pending, SyncJobStatus.running)),
        )
    )
    if active:
        raise ProviderError("Синхронизация Twilio уже выполняется")
    job = SyncJob(
        provider_id=provider.id,
        job_type=SyncJobType.twilio,
        status=SyncJobStatus.pending,
        triggered_by=triggered_by,
        stats={"progress": _progress_template()},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_latest_twilio_job(db: Session) -> SyncJob | None:
    return db.scalar(
        select(SyncJob)
        .where(SyncJob.job_type == SyncJobType.twilio)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )


def spawn_twilio_job(job_id: uuid.UUID) -> None:
    def _runner() -> None:
        try:
            asyncio.run(_execute(job_id))
        except Exception:
            logger.exception("Twilio sync thread crashed job_id=%s", job_id)

    threading.Thread(target=_runner, name=f"twilio-sync-{job_id}", daemon=True).start()


async def _execute(job_id: uuid.UUID) -> None:
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
        provider = db.scalar(
            select(Provider)
            .options(joinedload(Provider.connection))
            .where(Provider.code == ProviderCode.twilio)
        )
        if provider is None:
            job.status = SyncJobStatus.failed
            job.error_summary = "Twilio provider missing"
            job.finished_at = _now()
            db.commit()
            return

        job.status = SyncJobStatus.running
        job.started_at = _now()
        db.commit()

        _ping_lock_gated(lock_conn, lock_gate)
        keepalive_task = asyncio.create_task(
            _lock_keepalive(lock_conn, lock_gate, stop_keepalive),
            name=f"twilio-lock-keepalive-{job_id}",
        )
        client = TwilioClient(twilio_connection_config(provider))

        def page_progress(stage_id: str, unit: str):
            last = [0.0]

            def report(fetched: int, total: int | None) -> None:
                now = time.monotonic()
                if now - last[0] < PROGRESS_THROTTLE_SECONDS:
                    return
                last[0] = now
                detail = f"{fetched} из {total} {unit}" if total else f"{fetched} {unit}"
                _set_stage(job, stage_id, "running", detail)
                db.commit()

            return report

        _set_stage(job, "countries", "running")
        db.commit()
        countries = await client.list_countries(on_page=page_progress("countries", "стран"))
        _set_stage(job, "countries", "success", f"{len(countries)} стран")
        db.commit()

        _set_stage(job, "pricing", "running")
        db.commit()
        pricing_by_iso: dict[str, dict] = {}
        for index, country in enumerate(countries, start=1):
            payload = await client.fetch_pricing(country.country_iso)
            if payload:
                pricing_by_iso[country.country_iso] = payload
            if index == 1 or index % 10 == 0 or index == len(countries):
                _set_stage(job, "pricing", "running", f"{index} из {len(countries)} стран")
                db.commit()
        _set_stage(job, "pricing", "success", f"{len(pricing_by_iso)} прайсов")
        db.commit()

        rows = build_catalog_rows(countries, pricing_by_iso)
        _set_stage(job, "cutover", "running")
        db.commit()
        _ping_lock_gated(lock_conn, lock_gate)
        counts = persist_twilio_coverage(
            db,
            provider_id=provider.id,
            job_id=job.id,
            countries=[c.raw for c in countries],
            pricing_by_iso=pricing_by_iso,
            rows=rows,
        )
        _set_stage(job, "cutover", "success", f"{counts.get('rows', 0)} строк витрины")
        job.status = SyncJobStatus.success
        job.finished_at = _now()
        stats = dict(job.stats or {})
        stats["counts"] = counts
        job.stats = stats
        flag_modified(job, "stats")
        db.commit()
    except EmptyTwilioFetchError as exc:
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job:
            _set_stage(job, "cutover", "failed", exc.message)
            job.status = SyncJobStatus.failed
            job.error_summary = exc.message
            job.finished_at = _now()
            db.commit()
    except Exception as exc:
        logger.exception("Twilio sync failed")
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job:
            _fail_current_stage(job, str(exc))
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
                logger.exception("Twilio lock keepalive task failed on shutdown")
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
            logger.exception("Failed to close Twilio db session")
