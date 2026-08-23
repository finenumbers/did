"""DIDWW coverage catalog API — isolated from the RU unified sync endpoints."""

import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.sync import SyncJob
from app.modules.didww import (
    create_didww_job,
    didww_connection_config,
    get_didww_provider,
    get_latest_didww_job,
    spawn_didww_job,
)
from app.providers.didww.client import DidwwClient
from app.providers.didww.parser import collection_items
from app.providers.errors import ProviderError
from app.schemas.common import Page
from app.schemas.didww import (
    DidwwAvailableDidOut,
    DidwwFacetResponse,
    DidwwGroupItem,
    DidwwSyncJobOut,
    DidwwSyncStageOut,
)
from app.services.didww_service import DidwwCatalogService

router = APIRouter(prefix="/didww", tags=["DIDWW"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_filters_param(filters: str | None) -> dict[str, list[str]]:
    try:
        return DidwwCatalogService.parse_filters(filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _job_out(job: SyncJob) -> DidwwSyncJobOut:
    stats = job.stats or {}
    progress = stats.get("progress") or {}
    stages = [
        DidwwSyncStageOut(
            id=str(stage.get("id") or ""),
            group=str(stage.get("group") or "DIDWW"),
            label=str(stage.get("label") or ""),
            status=str(stage.get("status") or "pending"),
            detail=str(stage.get("detail") or ""),
            started_at=stage.get("started_at"),
            finished_at=stage.get("finished_at"),
        )
        for stage in progress.get("stages") or []
    ]
    return DidwwSyncJobOut(
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
    )


@router.get(
    "/groups",
    response_model=Page[DidwwGroupItem],
    summary="List DIDWW DID groups (coverage rows)",
    description=(
        "One row = one DIDWW DID Group in stock, not an E.164 number. "
        'Use filters JSON for multi-select column filters, e.g. {"country_iso":["GB"]}.'
    ),
)
def list_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("country_name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None, description='JSON object: {"country_iso":["GB"]}'),
    q: str | None = Query(None, description="Search by country / region / city / prefix"),
    db: Session = Depends(get_db),
) -> Page[DidwwGroupItem]:
    return DidwwCatalogService(db).list_groups(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=_parse_filters_param(filters),
        q=q,
    )


@router.get(
    "/facets",
    response_model=DidwwFacetResponse,
    summary="Column facet values for the DIDWW catalog",
)
def list_facets(
    column: str = Query(...),
    filters: str | None = Query(None),
    q: str | None = Query(None, description="Row-level search, same as on /groups"),
    value_q: str | None = Query(None, description="Search inside the facet values"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> DidwwFacetResponse:
    try:
        return DidwwCatalogService(db).list_facets(
            column=column,
            filters=_parse_filters_param(filters),
            q=q,
            value_q=value_q,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/export.xlsx",
    response_class=FileResponse,
    summary="Download the filtered DIDWW catalog as XLSX",
)
def export_xlsx(
    sort_by: str | None = Query("country_name"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
) -> FileResponse:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    DidwwCatalogService(db).write_xlsx(
        tmp.name,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=_parse_filters_param(filters),
        q=q,
    )
    return FileResponse(tmp.name, media_type=_XLSX_MEDIA, filename="didww-coverage.xlsx")


@router.post(
    "/sync",
    response_model=DidwwSyncJobOut,
    summary="Start the isolated DIDWW coverage sync",
)
def start_sync(db: Session = Depends(get_db)) -> DidwwSyncJobOut:
    try:
        job = create_didww_job(db, triggered_by="didww_page")
    except ProviderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    spawn_didww_job(job.id)
    return _job_out(job)


@router.get(
    "/sync/latest",
    response_model=DidwwSyncJobOut | None,
    summary="Latest DIDWW sync job with per-stage progress",
)
def latest_sync(db: Session = Depends(get_db)) -> DidwwSyncJobOut | None:
    job = get_latest_didww_job(db)
    return _job_out(job) if job else None


@router.get(
    "/available-dids",
    response_model=list[DidwwAvailableDidOut],
    summary="On-demand DIDWW available DIDs (never persisted)",
    description=(
        "Live read-only passthrough to GET /v3/available_dids. Results are not stored: "
        "the endpoint is optional per account, unpaginated and returns numbers in random order."
    ),
)
async def available_dids(
    did_group_id: str | None = Query(None),
    number_contains: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[DidwwAvailableDidOut]:
    provider = get_didww_provider(db)
    try:
        client = DidwwClient(didww_connection_config(provider))
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        payload = await client.list_available_dids(
            did_group_id=did_group_id,
            number_contains=number_contains,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.aclose()
    out: list[DidwwAvailableDidOut] = []
    for item in collection_items(payload):
        attrs = item.get("attributes") or {}
        group = ((item.get("relationships") or {}).get("did_group") or {}).get("data") or {}
        out.append(
            DidwwAvailableDidOut(
                id=str(item.get("id") or ""),
                number=attrs.get("number"),
                did_group_id=str(group.get("id")) if group.get("id") else None,
            )
        )
    return out
