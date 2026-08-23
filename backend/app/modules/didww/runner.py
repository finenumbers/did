"""Isolated DIDWW coverage sync — not part of unified RU provider order / finalize stages."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.db import SessionLocal, lock_engine
from app.models.enums import ProviderCode, SyncJobStatus, SyncJobType
from app.models.providers import Provider
from app.models.sync import SyncJob
from app.modules.didww.persist import EmptyDidwwFetchError, persist_didww_coverage
from app.modules.sync_engine.locks import advisory_unlock_conn, ping_lock_conn, try_advisory_lock_conn
from app.providers.didww.client import DidwwClient
from app.providers.didww.parser import parse_did_group
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)

DIDWW_LOCK_KEY = 88221003

STAGES = (
    ("countries", "Страны"),
    ("types", "Типы групп"),
    ("regions", "Регионы"),
    ("cities", "Города"),
    ("groups", "DID Groups"),
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
                "group": "DIDWW",
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


def didww_connection_config(provider: Provider) -> ConnectionConfig:
    conn = provider.connection
    if conn is None:
        raise ProviderError("DIDWW connection settings missing")
    return ConnectionConfig(
        base_url=conn.base_url,
        auth_settings=dict(conn.auth_settings or {}),
        extra_settings=dict(conn.extra_settings or {}),
    )


def get_didww_provider(db: Session) -> Provider:
    provider = db.scalar(
        select(Provider)
        .options(joinedload(Provider.connection))
        .where(Provider.code == ProviderCode.didww)
    )
    if provider is None:
        raise ProviderError("DIDWW provider is not seeded")
    return provider


def create_didww_job(db: Session, *, triggered_by: str = "api") -> SyncJob:
    provider = get_didww_provider(db)
    active = db.scalar(
        select(SyncJob).where(
            SyncJob.job_type == SyncJobType.didww,
            SyncJob.status.in_((SyncJobStatus.pending, SyncJobStatus.running)),
        )
    )
    if active:
        raise ProviderError("Синхронизация DIDWW уже выполняется")
    job = SyncJob(
        provider_id=provider.id,
        job_type=SyncJobType.didww,
        status=SyncJobStatus.pending,
        triggered_by=triggered_by,
        stats={"progress": _progress_template()},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_latest_didww_job(db: Session) -> SyncJob | None:
    return db.scalar(
        select(SyncJob)
        .where(SyncJob.job_type == SyncJobType.didww)
        .order_by(SyncJob.created_at.desc())
    )


def spawn_didww_job(job_id: uuid.UUID) -> None:
    def _runner() -> None:
        try:
            asyncio.run(_execute(job_id))
        except Exception:
            logger.exception("DIDWW sync thread crashed job_id=%s", job_id)

    threading.Thread(target=_runner, name=f"didww-sync-{job_id}", daemon=True).start()


async def _execute(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    lock_conn = None
    client: DidwwClient | None = None
    try:
        lock_conn = lock_engine.connect()
        if not try_advisory_lock_conn(lock_conn, DIDWW_LOCK_KEY):
            job = db.get(SyncJob, job_id)
            if job:
                job.status = SyncJobStatus.failed
                job.error_summary = "Синхронизация DIDWW уже выполняется (lock)"
                job.finished_at = _now()
                db.commit()
            return

        job = db.get(SyncJob, job_id)
        if job is None:
            return
        provider = db.scalar(
            select(Provider)
            .options(joinedload(Provider.connection))
            .where(Provider.code == ProviderCode.didww)
        )
        if provider is None:
            job.status = SyncJobStatus.failed
            job.error_summary = "DIDWW provider missing"
            job.finished_at = _now()
            db.commit()
            return

        job.status = SyncJobStatus.running
        job.started_at = _now()
        db.commit()

        ping_lock_conn(lock_conn)
        client = DidwwClient(didww_connection_config(provider))

        async def stage(stage_id: str, coro, fmt):
            _set_stage(job, stage_id, "running")
            db.commit()
            ping_lock_conn(lock_conn)
            result = await coro
            _set_stage(job, stage_id, "success", fmt(result))
            db.commit()
            return result

        countries = await stage(
            "countries",
            client.list_countries(),
            lambda rows: f"{len(rows)} стран",
        )
        types = await stage(
            "types",
            client.list_did_group_types(),
            lambda rows: f"{len(rows)} типов",
        )
        regions, _ridx = await stage(
            "regions",
            client.list_regions(),
            lambda pair: f"{len(pair[0])} регионов",
        )
        cities, _cidx = await stage(
            "cities",
            client.list_cities(),
            lambda pair: f"{len(pair[0])} городов",
        )
        group_resources, idx = await stage(
            "groups",
            client.list_did_groups(),
            lambda pair: f"{len(pair[0])} групп",
        )
        groups = [parse_did_group(item, idx) for item in group_resources if item.get("id")]

        _set_stage(job, "cutover", "running")
        db.commit()
        ping_lock_conn(lock_conn)
        counts = persist_didww_coverage(
            db,
            provider_id=provider.id,
            job_id=job.id,
            countries=countries,
            regions=regions,
            cities=cities,
            group_types=types,
            groups=groups,
        )
        _set_stage(job, "cutover", "success", f"{counts.get('groups', 0)} строк витрины")
        job.status = SyncJobStatus.success
        job.finished_at = _now()
        stats = dict(job.stats or {})
        stats["counts"] = counts
        job.stats = stats
        flag_modified(job, "stats")
        db.commit()
    except EmptyDidwwFetchError as exc:
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job:
            _set_stage(job, "cutover", "failed", exc.message)
            job.status = SyncJobStatus.failed
            job.error_summary = exc.message
            job.finished_at = _now()
            db.commit()
    except Exception as exc:
        logger.exception("DIDWW sync failed")
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job:
            job.status = SyncJobStatus.failed
            job.error_summary = str(exc)
            job.finished_at = _now()
            db.commit()
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.exception("Failed to close DIDWW client")
        if lock_conn is not None:
            try:
                advisory_unlock_conn(lock_conn, DIDWW_LOCK_KEY)
            except Exception:
                logger.exception("Failed to unlock DIDWW lock")
            try:
                lock_conn.close()
            except Exception:
                logger.exception("Failed to close DIDWW lock connection")
        try:
            db.close()
        except Exception:
            logger.exception("Failed to close DIDWW db session")
