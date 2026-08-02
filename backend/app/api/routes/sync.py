from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.enums import ProviderCode
from app.models.providers import Provider
from app.models.sync import SyncJob, SyncJobLog
from app.modules.sync_engine.modes import SyncMode
from app.modules.sync_engine.service import SyncService
from app.providers.errors import ProviderError
from app.schemas.common import Page
from app.schemas.sync import SyncJobOut, SyncLogOut, SyncStartRequest

router = APIRouter(tags=["Sync"])


def _job_out(db: Session, job: SyncJob) -> SyncJobOut:
    provider = db.get(Provider, job.provider_id)
    return SyncJobOut(
        id=job.id,
        provider_code=provider.code.value if provider else "unknown",
        job_type=job.job_type.value,
        status=job.status.value,
        started_at=job.started_at,
        finished_at=job.finished_at,
        stats=job.stats or {},
        error_summary=job.error_summary,
        triggered_by=job.triggered_by,
        created_at=job.created_at,
    )


@router.post(
    "/providers/{code}/sync",
    response_model=SyncJobOut,
    summary="Start sync job",
    description="Modes: full, free_only, purchased_only, dictionaries_only. "
    "Unsupported number modes for Runexis return PROVIDER_CAPABILITY_LIMITED.",
)
def start_sync(
    code: str, payload: SyncStartRequest, db: Session = Depends(get_db)
) -> SyncJobOut:
    job = SyncService(db).start_and_run(
        code,
        SyncMode(payload.mode),
        dry_run=payload.dry_run,
        include_dictionaries=payload.include_dictionaries,
    )
    return _job_out(db, job)


@router.get("/sync/jobs/{job_id}", response_model=SyncJobOut, summary="Get sync job status")
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> SyncJobOut:
    job = db.get(SyncJob, job_id)
    if not job:
        raise ProviderError("Sync job not found", code="SYNC_JOB_NOT_FOUND")
    return _job_out(db, job)


@router.get(
    "/sync/jobs/{job_id}/logs",
    response_model=Page[SyncLogOut],
    summary="Get sync job logs",
)
def get_logs(
    job_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: str | None = None,
    db: Session = Depends(get_db),
) -> Page[SyncLogOut]:
    stmt = select(SyncJobLog).where(SyncJobLog.sync_job_id == job_id)
    if level:
        stmt = stmt.where(SyncJobLog.level == level)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SyncJobLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        SyncLogOut(
            id=r.id,
            level=r.level.value,
            message=r.message,
            context=r.context or {},
            created_at=r.created_at,
        )
        for r in rows
    ]
    return Page.of(items, page=page, page_size=page_size, total=total)


@router.get(
    "/providers/{code}/sync/jobs",
    response_model=Page[SyncJobOut],
    summary="List recent sync jobs for provider",
)
def list_jobs(
    code: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Page[SyncJobOut]:
    provider = db.scalar(select(Provider).where(Provider.code == ProviderCode(code)))
    if not provider:
        raise ProviderError(f"Provider not found: {code}")
    stmt = select(SyncJob).where(SyncJob.provider_id == provider.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SyncJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page.of(
        [_job_out(db, j) for j in rows], page=page, page_size=page_size, total=total
    )
