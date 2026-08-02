import asyncio
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.core.db import get_db
from app.models.enums import InventoryKind
from app.schemas.common import Page
from app.schemas.numbers import FacetResponse, NumberItem
from app.services.numbers_export import export_xlsx_job
from app.services.numbers_service import NumbersService

router = APIRouter(prefix="/numbers", tags=["Numbers"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cleanup_tmp(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def _parse_filters_param(filters: str | None) -> dict[str, list[str]]:
    try:
        return NumbersService.parse_filters(filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _list(
    db: Session,
    kind: InventoryKind,
    page: int,
    page_size: int,
    sort_by: str | None,
    sort_dir: str,
    filters: str | None,
    number_local_q: str | None,
    msisdn_q: str | None,
    provider_number_key_q: str | None,
    provider: list[str] | None,
    region: str | None,
    city: str | None,
    status: str | None,
    price_min: Decimal | None,
    price_max: Decimal | None,
    q: str | None,
) -> Page[NumberItem]:
    return NumbersService(db).list_numbers(
        inventory_kind=kind,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=_parse_filters_param(filters),
        number_local_q=number_local_q,
        msisdn_q=msisdn_q,
        provider_number_key_q=provider_number_key_q,
        provider=provider,
        region=region,
        city=city,
        status=status,
        price_min=price_min,
        price_max=price_max,
        q=q,
    )


def _facets(
    db: Session,
    kind: InventoryKind,
    column: str,
    filters: str | None,
    number_local_q: str | None,
    msisdn_q: str | None,
    provider_number_key_q: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> FacetResponse:
    try:
        return NumbersService(db).list_facets(
            inventory_kind=kind,
            column=column,
            filters=_parse_filters_param(filters),
            number_local_q=number_local_q,
            msisdn_q=msisdn_q,
            provider_number_key_q=provider_number_key_q,
            q=q,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/free",
    response_model=Page[NumberItem],
    summary="List free numbers",
    description=(
        "Paginated free inventory from numbers_catalog_normalized. "
        "field_verification marks documentation_verified / example_confirmed / unresolved values. "
        "Use filters JSON for multi-select column filters; number_local_q for local number search."
    ),
)
def list_free(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("abc_code"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None, description='JSON object: {"region_name":["Москва"]}'),
    number_local_q: str | None = None,
    msisdn_q: str | None = None,
    provider_number_key_q: str | None = None,
    provider: list[str] | None = Query(None),
    region: str | None = None,
    city: str | None = None,
    status: str | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> Page[NumberItem]:
    return _list(
        db,
        InventoryKind.free,
        page,
        page_size,
        sort_by,
        sort_dir,
        filters,
        number_local_q,
        msisdn_q,
        provider_number_key_q,
        provider,
        region,
        city,
        status,
        price_min,
        price_max,
        q,
    )


@router.get(
    "/purchased",
    response_model=Page[NumberItem],
    summary="List purchased numbers",
    description="Paginated purchased inventory. SipOut source action: did/connected_list.",
)
def list_purchased(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str | None = Query("abc_code"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None, description='JSON object: {"doc_status":["ok"]}'),
    number_local_q: str | None = None,
    msisdn_q: str | None = None,
    provider_number_key_q: str | None = None,
    provider: list[str] | None = Query(None),
    region: str | None = None,
    city: str | None = None,
    status: str | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> Page[NumberItem]:
    return _list(
        db,
        InventoryKind.purchased,
        page,
        page_size,
        sort_by,
        sort_dir,
        filters,
        number_local_q,
        msisdn_q,
        provider_number_key_q,
        provider,
        region,
        city,
        status,
        price_min,
        price_max,
        q,
    )


async def _export_xlsx(
    kind: InventoryKind,
    *,
    filters: str | None,
    number_local_q: str | None,
    sort_by: str | None,
    sort_dir: str,
    filename: str,
) -> FileResponse:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp_path = tmp.name
    tmp.close()
    try:
        await asyncio.to_thread(
            export_xlsx_job,
            inventory_kind=kind,
            path=tmp_path,
            filters=_parse_filters_param(filters),
            number_local_q=number_local_q,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except Exception:
        _cleanup_tmp(tmp_path)
        raise
    return FileResponse(
        tmp_path,
        media_type=_XLSX_MEDIA,
        filename=filename,
        background=BackgroundTask(_cleanup_tmp, tmp_path),
    )


@router.get(
    "/free/export.xlsx",
    summary="Export free numbers to XLSX",
    response_class=FileResponse,
)
async def export_free_xlsx(
    sort_by: str | None = Query("abc_code"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None),
    number_local_q: str | None = None,
) -> FileResponse:
    return await _export_xlsx(
        InventoryKind.free,
        filters=filters,
        number_local_q=number_local_q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filename="free_numbers.xlsx",
    )


@router.get(
    "/purchased/export.xlsx",
    summary="Export purchased numbers to XLSX",
    response_class=FileResponse,
)
async def export_purchased_xlsx(
    sort_by: str | None = Query("abc_code"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    filters: str | None = Query(None),
    number_local_q: str | None = None,
) -> FileResponse:
    return await _export_xlsx(
        InventoryKind.purchased,
        filters=filters,
        number_local_q=number_local_q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filename="purchased_numbers.xlsx",
    )


@router.get(
    "/free/facets",
    response_model=FacetResponse,
    summary="Facet values for a free-numbers column",
)
def free_facets(
    column: str = Query(..., description="Catalog column key (not msisdn / provider_number_key)"),
    filters: str | None = Query(None),
    number_local_q: str | None = None,
    msisdn_q: str | None = None,
    provider_number_key_q: str | None = None,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> FacetResponse:
    return _facets(
        db,
        InventoryKind.free,
        column,
        filters,
        number_local_q,
        msisdn_q,
        provider_number_key_q,
        q,
        limit,
        offset,
    )


@router.get(
    "/purchased/facets",
    response_model=FacetResponse,
    summary="Facet values for a purchased-numbers column",
)
def purchased_facets(
    column: str = Query(..., description="Catalog column key (not msisdn / provider_number_key)"),
    filters: str | None = Query(None),
    number_local_q: str | None = None,
    msisdn_q: str | None = None,
    provider_number_key_q: str | None = None,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> FacetResponse:
    return _facets(
        db,
        InventoryKind.purchased,
        column,
        filters,
        number_local_q,
        msisdn_q,
        provider_number_key_q,
        q,
        limit,
        offset,
    )
