from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.sync import SyncRun, SyncRunLog
from app.modules.sync_engine.dropped_export import (
    dropped_xlsx_exists,
    dropped_xlsx_path,
)
from app.modules.sync_engine.run_file_log import (
    sync_debug_log_exists,
    sync_debug_log_path,
)
from app.modules.sync_engine.progress import build_initial_progress
from app.modules.sync_engine.unified import (
    create_run,
    get_latest_run,
    spawn_unified_run,
)
from app.providers.errors import ProviderError
from app.schemas.common import Page
from app.schemas.sync import (
    StageProgressOut,
    SyncLogOut,
    SyncProgressOut,
    SyncRunOut,
    SyncStageOut,
)

router = APIRouter(tags=["Sync"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _run_out(run: SyncRun) -> SyncRunOut:
    progress = run.progress or build_initial_progress()
    stages = []
    for s in progress.get("stages") or []:
        prog = s.get("progress") or {}
        stages.append(
            SyncStageOut(
                id=s.get("id", ""),
                group=s.get("group", ""),
                label=s.get("label", ""),
                status=s.get("status", "pending"),
                detail=s.get("detail") or "",
                substage=s.get("substage") or "",
                progress=StageProgressOut(
                    current=prog.get("current"),
                    total=prog.get("total"),
                    unit=prog.get("unit") or "",
                ),
                started_at=s.get("started_at"),
                finished_at=s.get("finished_at"),
            )
        )
    return SyncRunOut(
        id=run.id,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        progress=SyncProgressOut(
            current_stage_id=progress.get("current_stage_id"),
            stages=stages,
        ),
        stats=run.stats or {},
        error_summary=run.error_summary,
        triggered_by=run.triggered_by,
        created_at=run.created_at,
    )


@router.post(
    "/sync/start",
    response_model=SyncRunOut,
    summary="Start unified sync of all providers",
)
def start_unified_sync(db: Session = Depends(get_db)) -> SyncRunOut:
    run = create_run(db, triggered_by="api")
    spawn_unified_run(run.id)
    return _run_out(run)


@router.get(
    "/sync/latest",
    response_model=SyncRunOut | None,
    summary="Get latest unified sync run",
)
def get_latest_unified_sync(db: Session = Depends(get_db)) -> SyncRunOut | None:
    run = get_latest_run(db)
    if not run:
        return None
    return _run_out(run)


@router.get(
    "/sync/runs/{run_id}",
    response_model=SyncRunOut,
    summary="Get unified sync run",
)
def get_unified_sync_run(run_id: UUID, db: Session = Depends(get_db)) -> SyncRunOut:
    run = db.get(SyncRun, run_id)
    if not run:
        raise ProviderError("Sync run not found", code="SYNC_RUN_NOT_FOUND")
    return _run_out(run)


@router.get(
    "/sync/dropped.xlsx",
    response_class=FileResponse,
    summary="Download latest sync dropped-numbers XLSX (unmapped + duplicates)",
)
def download_sync_dropped_xlsx() -> FileResponse:
    path = dropped_xlsx_path()
    if not dropped_xlsx_exists():
        raise ProviderError(
            "Отчёт по отброшенным номерам ещё не создан — выполните синхронизацию",
            code="SYNC_DROPPED_EXPORT_MISSING",
        )
    return FileResponse(
        path,
        media_type=_XLSX_MEDIA,
        filename="sync-dropped-latest.xlsx",
    )


@router.get(
    "/sync/debug.log",
    response_class=FileResponse,
    summary="Download latest sync debug log (overwritten each sync; partial while running)",
)
def download_sync_debug_log() -> FileResponse:
    path = sync_debug_log_path()
    if not sync_debug_log_exists():
        raise ProviderError(
            "Debug-лог синхронизации ещё не создан — выполните синхронизацию",
            code="SYNC_DEBUG_LOG_MISSING",
        )
    return FileResponse(
        path,
        media_type="text/plain; charset=utf-8",
        filename="sync-latest.log",
    )


@router.get(
    "/sync/runs/{run_id}/logs",
    response_model=Page[SyncLogOut],
    summary="Get unified sync run logs",
)
def get_unified_sync_logs(
    run_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: str | None = None,
    db: Session = Depends(get_db),
) -> Page[SyncLogOut]:
    run = db.get(SyncRun, run_id)
    if not run:
        raise ProviderError("Sync run not found", code="SYNC_RUN_NOT_FOUND")
    stmt = select(SyncRunLog).where(SyncRunLog.sync_run_id == run_id)
    if level:
        stmt = stmt.where(SyncRunLog.level == level)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SyncRunLog.created_at.desc())
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
