"""Twilio coverage + persisted sample numbers API — isolated from RU unified sync."""

import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.enums import SyncJobStatus
from app.models.sync import SyncJob
from app.modules.twilio import (
    create_twilio_job,
    get_latest_success_twilio_job,
    get_latest_twilio_job,
    get_twilio_provider,
    spawn_twilio_job,
    twilio_connection_config,
)
from app.modules.twilio.persist import catalog_progress_rows, snapshot_totals
from app.providers.errors import ProviderAuthError, ProviderError
from app.providers.twilio import contract as twilio_contract
from app.providers.twilio.client import TwilioClient
from app.schemas.common import Page
from app.schemas.twilio import (
    TwilioAvailableNumberOut,
    TwilioAvailableNumbersResponse,
    TwilioCoverageItem,
    TwilioFacetResponse,
    TwilioNumberItem,
    TwilioSyncJobOut,
    TwilioSyncStageOut,
)
from app.services.twilio_service import TwilioCatalogService, TwilioNumbersService

router = APIRouter(prefix="/twilio", tags=["Twilio"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_filters_param(filters: str | None) -> dict[str, list[str]]:
    try:
        return TwilioCatalogService.parse_filters(filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _job_out(job: SyncJob, *, last_success_at=None) -> TwilioSyncJobOut:
    stats = job.stats or {}
    progress = stats.get("progress") or {}
    stages = [
        TwilioSyncStageOut(
            id=str(stage.get("id") or ""),
            group=str(stage.get("group") or "Twilio"),
            label=str(stage.get("label") or ""),
            status=str(stage.get("status") or "pending"),
            detail=str(stage.get("detail") or ""),
            started_at=stage.get("started_at"),
            finished_at=stage.get("finished_at"),
        )
        for stage in progress.get("stages") or []
    ]
    return TwilioSyncJobOut(
        id=job.id,
        status=job.status.value,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_summary=job.error_summary,
        triggered_by=job.triggered_by,
        created_at=job.created_at,
        counts=stats.get("counts") or {},
        progress=progress,
        stages=stages,
        last_success_at=last_success_at,
    )


@router.get(
    "/coverage",
    response_model=Page[TwilioCoverageItem],
    summary="List Twilio coverage rows (country + type)",
)
def list_coverage(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("country_name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Page[TwilioCoverageItem]:
    return TwilioCatalogService(db).list_coverage(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=_parse_filters_param(filters),
        q=q,
    )


@router.get(
    "/numbers",
    response_model=Page[TwilioNumberItem],
    summary="List persisted Twilio sample numbers",
)
def list_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("country_name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Page[TwilioNumberItem]:
    return TwilioNumbersService(db).list_numbers(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=_parse_filters_param(filters),
        q=q,
    )


@router.get("/facets", response_model=TwilioFacetResponse)
def list_facets(
    column: str = Query(...),
    filters: str | None = Query(None),
    q: str | None = Query(None),
    value_q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> TwilioFacetResponse:
    try:
        return TwilioNumbersService(db).list_facets(
            column=column,
            filters=_parse_filters_param(filters),
            q=q,
            value_q=value_q,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export.xlsx", response_class=FileResponse)
def export_xlsx(
    sort_by: str | None = Query("country_name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> FileResponse:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    TwilioNumbersService(db).write_xlsx(
        tmp.name,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=_parse_filters_param(filters),
        q=q,
    )
    return FileResponse(tmp.name, media_type=_XLSX_MEDIA, filename="twilio-numbers.xlsx")


@router.post("/sync", response_model=TwilioSyncJobOut)
def start_sync(db: Session = Depends(get_db)) -> TwilioSyncJobOut:
    try:
        job = create_twilio_job(db, triggered_by="twilio_page")
    except ProviderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    spawn_twilio_job(job.id)
    success = get_latest_success_twilio_job(db)
    return _job_out(job, last_success_at=success.finished_at if success else None)


@router.get("/sync/latest", response_model=TwilioSyncJobOut | None)
def latest_sync(db: Session = Depends(get_db)) -> TwilioSyncJobOut | None:
    job = get_latest_twilio_job(db)
    if job is None:
        return None
    success = get_latest_success_twilio_job(db)
    out = _job_out(job, last_success_at=success.finished_at if success else None)
    if job.status == SyncJobStatus.success:
        provider = get_twilio_provider(db)
        progress = dict(out.progress or {})
        progress["rows"] = catalog_progress_rows(db, provider_id=provider.id)
        totals = snapshot_totals(db, provider_id=provider.id)
        summary = dict(progress.get("summary") or {})
        summary["cities_total"] = totals["cities_total"]
        summary["numbers_unique"] = totals["numbers_unique"]
        if summary.get("requests_total") is None and summary.get("requests") is not None:
            summary["requests_total"] = summary["requests"]
        progress["summary"] = summary
        out.progress = progress
    return out


@router.get(
    "/available-numbers",
    response_model=TwilioAvailableNumbersResponse,
    summary="On-demand Twilio available numbers (never persisted)",
)
async def available_numbers(
    country: str = Query(..., min_length=2, max_length=2),
    type: str = Query(..., alias="type"),
    in_region: str | None = Query(None),
    in_locality: str | None = Query(None),
    area_code: str | None = Query(None),
    contains: str | None = Query(None),
    db: Session = Depends(get_db),
) -> TwilioAvailableNumbersResponse:
    number_type = type.strip()
    if number_type not in twilio_contract.SEARCH_TYPE_PATHS:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип Twilio: {number_type}")
    provider = get_twilio_provider(db)
    try:
        client = TwilioClient(twilio_connection_config(provider))
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        rows = await client.search_available(
            country_iso=country.strip().upper(),
            number_type=number_type,
            in_region=in_region.strip() if in_region else None,
            in_locality=in_locality.strip() if in_locality else None,
            area_code=area_code.strip() if area_code else None,
            contains=contains.strip() if contains else None,
        )
    except ProviderAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.aclose()
    items: list[TwilioAvailableNumberOut] = []
    for row in rows:
        caps = row.get("capabilities") or {}
        if not isinstance(caps, dict):
            caps = {}
        items.append(
            TwilioAvailableNumberOut(
                phone_number=row.get("phone_number"),
                friendly_name=row.get("friendly_name"),
                iso_country=row.get("iso_country"),
                region=row.get("region"),
                locality=row.get("locality"),
                postal_code=row.get("postal_code"),
                lata=row.get("lata"),
                rate_center=row.get("rate_center"),
                address_requirements=row.get("address_requirements"),
                beta=row.get("beta"),
                voice=caps.get("voice"),
                sms=caps.get("sms") if "sms" in caps else caps.get("SMS"),
                mms=caps.get("mms") if "mms" in caps else caps.get("MMS"),
                fax=caps.get("fax"),
            )
        )
    return TwilioAvailableNumbersResponse(items=items, returned=len(items))
