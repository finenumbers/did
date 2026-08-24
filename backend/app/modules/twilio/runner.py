"""Isolated Twilio geo-sample sync — not part of unified RU provider order."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
from app.modules.twilio.persist import (
    EmptyTwilioFetchError,
    cutover_geo_snapshot,
    fill_number_counts,
    ingest_available_batch,
    number_count_for_row,
    number_counts_by_type,
    persist_twilio_coverage,
    refresh_local_counts,
    snapshot_totals,
    wipe_twilio_data,
)
from app.providers.dto.common import ConnectionConfig
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.twilio.client import TwilioClient
from app.providers.twilio.parser import CatalogRow, build_catalog_rows

logger = logging.getLogger(__name__)

TWILIO_LOCK_KEY = 88221004
LOCK_KEEPALIVE_SECONDS = 30
PROGRESS_THROTTLE_SECONDS = 2.0
TWILIO_JOB_TYPES = (SyncJobType.twilio, SyncJobType.twilio_numbers)

STAGES = (
    ("countries", "Страны"),
    ("pricing", "Цены"),
    ("sample", "Выборка"),
    ("cutover", "Запись каталога"),
)

STALE_JOB_MESSAGE = "прервано, процесс перезапущен"
RECLAIM_PENDING_GRACE = timedelta(seconds=60)


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
        "summary": {
            "requests": 0,
            "requests_total": None,
            "cities_total": 0,
            "numbers_unique": 0,
        },
        "current": {"country_iso": None, "in_region": None, "contains": None},
        "rows": [],
    }


def _ensure_progress(job: SyncJob) -> dict[str, Any]:
    stats = dict(job.stats or {})
    progress = stats.get("progress") or _progress_template()
    progress.setdefault(
        "summary",
        {"requests": 0, "requests_total": None, "cities_total": 0, "numbers_unique": 0},
    )
    progress.setdefault("current", {"country_iso": None, "in_region": None, "contains": None})
    progress.setdefault("rows", [])
    progress.setdefault("stages", [])
    stats["progress"] = progress
    job.stats = stats
    return progress


def _set_stage(job: SyncJob, stage_id: str, status: str, detail: str = "") -> None:
    progress = _ensure_progress(job)
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
    flag_modified(job, "stats")


def _fail_current_stage(job: SyncJob, message: str) -> None:
    progress = (job.stats or {}).get("progress") or {}
    stage_id = progress.get("current_stage_id")
    if stage_id:
        _set_stage(job, str(stage_id), "failed", message[:500])


def _price_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _row_payload(
    row: CatalogRow,
    *,
    status: str = "pending",
    detail: str = "",
    region_count: int = 0,
    city_count: int = 0,
) -> dict[str, Any]:
    return {
        "country_iso": row.country_iso,
        "country_name": row.country_name,
        "number_type": row.number_type,
        "status": status,
        "detail": detail,
        "region_count": region_count,
        "city_count": city_count,
        "number_count": 0,
        "period_price": _price_text(row.period_price),
        "price_unit": row.price_unit,
    }


def _find_row(rows: list[dict[str, Any]], country_iso: str, number_type: str) -> dict[str, Any] | None:
    iso = (country_iso or "").strip().upper()
    ntype = (number_type or "").strip()
    for item in rows:
        if (str(item.get("country_iso") or "").strip().upper() == iso
            and str(item.get("number_type") or "").strip() == ntype):
            return item
    return None


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


def get_active_twilio_job(db: Session) -> SyncJob | None:
    return db.scalar(
        select(SyncJob).where(
            SyncJob.job_type.in_(TWILIO_JOB_TYPES),
            SyncJob.status.in_((SyncJobStatus.pending, SyncJobStatus.running)),
        )
    )


def list_active_twilio_jobs(db: Session) -> list[SyncJob]:
    return list(
        db.scalars(
            select(SyncJob).where(
                SyncJob.job_type.in_(TWILIO_JOB_TYPES),
                SyncJob.status.in_((SyncJobStatus.pending, SyncJobStatus.running)),
            )
        ).all()
    )


def twilio_lock_is_free() -> bool:
    lock_conn = lock_engine.connect()
    try:
        if not try_advisory_lock_conn(lock_conn, TWILIO_LOCK_KEY):
            return False
        advisory_unlock_conn(lock_conn, TWILIO_LOCK_KEY)
        return True
    finally:
        lock_conn.close()


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _should_reclaim_job(job: SyncJob, now: datetime) -> bool:
    if job.status == SyncJobStatus.running:
        return True
    if job.status != SyncJobStatus.pending:
        return False
    created = _aware(getattr(job, "created_at", None))
    if created is None:
        return True
    return now - created >= RECLAIM_PENDING_GRACE


def reclaim_stale_twilio_jobs(db: Session, *, lock_free: bool | None = None) -> int:
    jobs = list_active_twilio_jobs(db)
    if not jobs:
        return 0
    if lock_free is None:
        lock_free = twilio_lock_is_free()
    if not lock_free:
        return 0
    now = _now()
    reclaimed = 0
    for job in jobs:
        if not _should_reclaim_job(job, now):
            continue
        job.status = SyncJobStatus.failed
        job.error_summary = STALE_JOB_MESSAGE
        job.finished_at = now
        reclaimed += 1
    if reclaimed:
        db.commit()
    return reclaimed


def wipe_twilio_locked(db: Session) -> dict[str, int]:
    lock_conn = lock_engine.connect()
    acquired = False
    try:
        acquired = try_advisory_lock_conn(lock_conn, TWILIO_LOCK_KEY)
        if not acquired:
            raise ProviderError("Синхронизация Twilio уже выполняется")
        reclaim_stale_twilio_jobs(db, lock_free=True)
        provider = get_twilio_provider(db)
        return wipe_twilio_data(db, provider_id=provider.id)
    finally:
        if acquired:
            try:
                advisory_unlock_conn(lock_conn, TWILIO_LOCK_KEY)
            except Exception:
                logger.exception("Failed to unlock Twilio lock after wipe")
        try:
            lock_conn.close()
        except Exception:
            logger.exception("Failed to close Twilio lock connection after wipe")


def create_twilio_job(db: Session, *, triggered_by: str = "api") -> SyncJob:
    provider = get_twilio_provider(db)
    reclaim_stale_twilio_jobs(db)
    if get_active_twilio_job(db):
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


def get_latest_success_twilio_job(db: Session) -> SyncJob | None:
    return db.scalar(
        select(SyncJob)
        .where(
            SyncJob.job_type == SyncJobType.twilio,
            SyncJob.status == SyncJobStatus.success,
        )
        .order_by(SyncJob.finished_at.desc())
        .limit(1)
    )


def spawn_twilio_job(job_id: uuid.UUID) -> None:
    def _runner() -> None:
        try:
            asyncio.run(_execute(job_id))
        except Exception:
            logger.exception("Twilio sync thread crashed job_id=%s", job_id)

    threading.Thread(target=_runner, name=f"twilio-sync-{job_id}", daemon=True).start()


class _Progress:
    def __init__(self, db: Session, job: SyncJob):
        self.db = db
        self.job = job
        self.last_flush = 0.0
        self.requests = 0
        self.requests_total: int | None = None
        self.phones: set[str] = set()
        self.phones_by_row: dict[tuple[str, str], set[str]] = {}
        self.cities: set[tuple[str, str, str]] = set()

    def bump_request(self) -> None:
        self.requests += 1

    def note_batch(self, country_iso: str, number_type: str, result: dict[str, Any]) -> None:
        phones = result.get("phones") or ()
        self.phones.update(phones)
        self.phones_by_row.setdefault((country_iso, number_type), set()).update(phones)
        for region_filter, locality in result.get("cities") or ():
            self.cities.add((country_iso, region_filter, locality))

    def row_number_count(self, country_iso: str, number_type: str) -> int:
        return len(self.phones_by_row.get((country_iso, number_type), set()))

    def apply(
        self,
        *,
        current: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        force: bool = False,
        stage_id: str | None = None,
        stage_status: str | None = None,
        stage_detail: str = "",
    ) -> None:
        progress = _ensure_progress(self.job)
        progress["summary"] = {
            "requests": self.requests,
            "requests_total": self.requests_total,
            "cities_total": len(self.cities),
            "numbers_unique": len(self.phones),
        }
        if current is not None:
            progress["current"] = current
        if rows is not None:
            progress["rows"] = rows
        if stage_id and stage_status:
            _set_stage(self.job, stage_id, stage_status, stage_detail)
        flag_modified(self.job, "stats")
        now = time.monotonic()
        if not force and now - self.last_flush < PROGRESS_THROTTLE_SECONDS:
            return
        self.last_flush = now
        self.db.commit()


async def _search_or_empty(
    client: TwilioClient,
    *,
    country_iso: str,
    number_type: str,
    in_region: str | None = None,
    in_locality: str | None = None,
    contains: str | None = None,
) -> list[dict[str, Any]]:
    try:
        return await client.search_available(
            country_iso=country_iso,
            number_type=number_type,
            in_region=in_region,
            in_locality=in_locality,
            contains=contains,
        )
    except ProviderAuthError:
        raise
    except ProviderError as exc:
        status = (exc.details or {}).get("status")
        if isinstance(status, int) and status == 429:
            raise
        if isinstance(status, int) and 400 <= status < 500:
            logger.warning(
                "Twilio search %s %s in_region=%s contains=%s HTTP %s; treat as empty",
                country_iso,
                number_type,
                in_region,
                contains,
                status,
            )
            return []
        raise


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
            if job and job.status == SyncJobStatus.pending:
                job.status = SyncJobStatus.failed
                job.error_summary = "Синхронизация Twilio уже выполняется (lock)"
                job.finished_at = _now()
                db.commit()
            return

        job = db.get(SyncJob, job_id)
        if job is None or job.status != SyncJobStatus.pending:
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
        _ensure_progress(job)
        db.commit()

        _ping_lock_gated(lock_conn, lock_gate)
        keepalive_task = asyncio.create_task(
            _lock_keepalive(lock_conn, lock_gate, stop_keepalive),
            name=f"twilio-lock-keepalive-{job_id}",
        )
        client = TwilioClient(twilio_connection_config(provider))
        tracker = _Progress(db, job)

        _set_stage(job, "countries", "running")
        db.commit()
        countries = await client.list_countries(on_page=lambda *_args: tracker.bump_request())
        rows = build_catalog_rows(countries, {})
        progress_rows = [_row_payload(row) for row in rows]
        fill_number_counts(progress_rows, number_counts_by_type(db, provider_id=provider.id))
        tracker.apply(
            rows=progress_rows,
            force=True,
            stage_id="countries",
            stage_status="success",
            stage_detail=f"{len(countries)} стран · {len(progress_rows)} строк",
        )

        _set_stage(job, "pricing", "running")
        db.commit()
        pricing_by_iso: dict[str, dict] = {}
        for index, country in enumerate(countries, start=1):
            payload = await client.fetch_pricing(country.country_iso)
            tracker.bump_request()
            if payload:
                pricing_by_iso[country.country_iso] = payload
            if index == 1 or index % 10 == 0 or index == len(countries):
                tracker.apply(
                    force=True,
                    stage_id="pricing",
                    stage_status="running",
                    stage_detail=f"{index} из {len(countries)} стран",
                )
        priced_rows = build_catalog_rows(countries, pricing_by_iso)
        progress_rows = [_row_payload(row) for row in priced_rows]
        fill_number_counts(progress_rows, number_counts_by_type(db, provider_id=provider.id))
        tracker.apply(
            rows=progress_rows,
            force=True,
            stage_id="pricing",
            stage_status="success",
            stage_detail=f"{len(pricing_by_iso)} прайсов",
        )

        _set_stage(job, "sample", "running")
        db.commit()
        tracker.requests_total = tracker.requests + len(priced_rows)
        tracker.apply(
            rows=progress_rows,
            force=True,
            stage_id="sample",
            stage_status="running",
            stage_detail=f"0 / {len(priced_rows)}",
        )
        for index, row in enumerate(priced_rows, start=1):
            item = _find_row(progress_rows, row.country_iso, row.number_type)
            if item:
                item["status"] = "running"
                item["detail"] = "0 / 1"
            batch = await _search_or_empty(
                client,
                country_iso=row.country_iso,
                number_type=row.number_type,
            )
            tracker.bump_request()
            result = ingest_available_batch(
                db,
                provider_id=provider.id,
                job_id=job.id,
                country_iso=row.country_iso,
                country_name=row.country_name,
                number_type=row.number_type,
                region_filter="",
                items=batch,
            )
            tracker.note_batch(row.country_iso, row.number_type, result)
            if item:
                item["status"] = "success"
                item["detail"] = ""
                item["number_count"] = tracker.row_number_count(row.country_iso, row.number_type)
                item["region_count"] = len(result.get("regions") or ())
                item["city_count"] = len(result.get("cities") or ())
                if not batch:
                    item["number_count"] = 0
            tracker.apply(
                current={
                    "country_iso": row.country_iso,
                    "in_region": None,
                    "contains": None,
                },
                rows=progress_rows,
                stage_id="sample",
                stage_status="running",
                stage_detail=f"{index} / {len(priced_rows)}",
            )
        tracker.apply(
            rows=progress_rows,
            force=True,
            stage_id="sample",
            stage_status="success",
            stage_detail=f"{len(priced_rows)} строк",
        )

        _set_stage(job, "cutover", "running")
        db.commit()
        _ping_lock_gated(lock_conn, lock_gate)
        counts = persist_twilio_coverage(
            db,
            provider_id=provider.id,
            job_id=job.id,
            countries=[c.raw for c in countries],
            pricing_by_iso=pricing_by_iso,
            rows=priced_rows,
        )
        wipe = cutover_geo_snapshot(db, provider_id=provider.id, job_id=job.id)
        for row in priced_rows:
            item = _find_row(progress_rows, row.country_iso, row.number_type)
            if item:
                _refresh_row_counts(db, tracker, item, row)
                item["status"] = "success"
                item["detail"] = ""
        totals = snapshot_totals(db, provider_id=provider.id)
        tracker.phones = set()
        tracker.cities = set()
        tracker.apply(
            rows=progress_rows,
            current={"country_iso": None, "in_region": None, "contains": None},
            force=True,
            stage_id="cutover",
            stage_status="success",
            stage_detail=f"{counts.get('rows', 0)} строк витрины",
        )
        progress = _ensure_progress(job)
        progress["summary"] = {
            "requests": tracker.requests,
            "requests_total": tracker.requests_total or tracker.requests,
            "cities_total": totals["cities_total"],
            "numbers_unique": totals["numbers_unique"],
        }
        job.status = SyncJobStatus.success
        job.finished_at = _now()
        stats = dict(job.stats or {})
        stats["counts"] = {
            **counts,
            **wipe,
            **totals,
            "requests": tracker.requests,
        }
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


def _refresh_row_counts(
    db: Session,
    tracker: _Progress,
    item: dict[str, Any],
    row: CatalogRow,
) -> None:
    region_count, city_count = refresh_local_counts(
        db,
        provider_id=tracker.job.provider_id,
        country_iso=row.country_iso,
        number_type=row.number_type,
    )
    item["region_count"] = region_count
    item["city_count"] = city_count
    item["number_count"] = number_count_for_row(
        db,
        provider_id=tracker.job.provider_id,
        country_iso=row.country_iso,
        number_type=row.number_type,
    )
