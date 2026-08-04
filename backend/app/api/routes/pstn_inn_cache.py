from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.pstn_inn_cache import service as cache_svc
from app.schemas.pstn_inn_cache import (
    PstnInnCacheStatusOut,
    PstnInnOperatorIn,
    PstnInnOperatorOut,
    PstnInnOperatorUpdate,
    SyncScheduleOut,
    SyncScheduleUpdate,
)

router = APIRouter(tags=["PSTN INN cache"])


@router.get(
    "/settings/pstn-inn-cache",
    response_model=PstnInnCacheStatusOut,
    summary="Status of local PSTN INN ranges cache (operator column only)",
)
def get_pstn_inn_cache(db: Session = Depends(get_db)) -> PstnInnCacheStatusOut:
    return PstnInnCacheStatusOut(**cache_svc.get_cache_status(db))


@router.post(
    "/settings/pstn-inn-cache/operators",
    response_model=PstnInnOperatorOut,
    summary="Add operator to cache list",
)
def add_operator(payload: PstnInnOperatorIn, db: Session = Depends(get_db)) -> PstnInnOperatorOut:
    op = cache_svc.add_operator(db, name=payload.name, inn=payload.inn, enabled=payload.enabled)
    status = cache_svc.get_cache_status(db)
    return next(o for o in status["operators"] if o["inn"] == op.inn)


@router.patch(
    "/settings/pstn-inn-cache/operators/{inn}",
    response_model=PstnInnOperatorOut,
    summary="Update operator (name/enabled); required cannot be disabled",
)
def patch_operator(
    inn: str, payload: PstnInnOperatorUpdate, db: Session = Depends(get_db)
) -> PstnInnOperatorOut:
    op = cache_svc.update_operator(db, inn, name=payload.name, enabled=payload.enabled)
    status = cache_svc.get_cache_status(db)
    return next(o for o in status["operators"] if o["inn"] == op.inn)


@router.delete(
    "/settings/pstn-inn-cache/operators/{inn}",
    summary="Delete non-required operator and its cached ranges",
)
def delete_operator(inn: str, db: Session = Depends(get_db)) -> dict:
    cache_svc.delete_operator(db, inn)
    return {"ok": True}


@router.post(
    "/settings/pstn-inn-cache/refresh",
    response_model=PstnInnCacheStatusOut,
    summary="Manually refresh enabled INN ranges into local cache",
)
def refresh_cache(db: Session = Depends(get_db)) -> PstnInnCacheStatusOut:
    cache_svc.spawn_cache_refresh()
    return PstnInnCacheStatusOut(**cache_svc.get_cache_status(db))


@router.get(
    "/settings/sync-schedule",
    response_model=SyncScheduleOut,
    summary="Daily sync schedule (Europe/Moscow 00:00)",
)
def get_sync_schedule(db: Session = Depends(get_db)) -> SyncScheduleOut:
    return SyncScheduleOut(**cache_svc.get_sync_schedule(db))


@router.put(
    "/settings/sync-schedule",
    response_model=SyncScheduleOut,
    summary="Enable/disable daily sync schedule",
)
def put_sync_schedule(
    payload: SyncScheduleUpdate, db: Session = Depends(get_db)
) -> SyncScheduleOut:
    return SyncScheduleOut(**cache_svc.set_sync_schedule(db, enabled=payload.enabled))
