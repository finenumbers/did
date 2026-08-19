import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.common import Page
from app.schemas.mask_types import MaskTypeItem, MaskTypesLoadResult
from app.schemas.numbers import FacetResponse
from app.services.mask_types_service import MAX_IMPORT_BYTES, MaskTypesService

router = APIRouter(prefix="/mask-types", tags=["Mask types"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_filters_param(filters: str | None) -> dict[str, list[str]]:
    try:
        return MaskTypesService.parse_filters(filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "",
    response_model=Page[MaskTypeItem],
    summary="Mask types directory",
)
def list_mask_types(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    mask_q: str | None = None,
    filters: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Page[MaskTypeItem]:
    return MaskTypesService(db).list_page(
        page=page,
        page_size=page_size,
        mask_q=mask_q,
        filters=_parse_filters_param(filters),
    )


@router.get(
    "/facets",
    response_model=FacetResponse,
    summary="Facet values for a mask-types column",
)
def mask_type_facets(
    column: str = Query(...),
    filters: str | None = Query(None),
    mask_q: str | None = None,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> FacetResponse:
    try:
        return MaskTypesService(db).list_facets(
            column=column,
            filters=_parse_filters_param(filters),
            mask_q=mask_q,
            q=q,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/export.xlsx",
    response_class=FileResponse,
    summary="Download mask types as XLSX",
)
def export_mask_types_xlsx(db: Session = Depends(get_db)) -> FileResponse:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    MaskTypesService(db).write_xlsx(tmp.name)
    return FileResponse(
        tmp.name,
        media_type=_XLSX_MEDIA,
        filename="masks.xlsx",
    )


@router.post(
    "/import.xlsx",
    response_model=MaskTypesLoadResult,
    summary="Upsert mask types from XLSX",
)
async def import_mask_types_xlsx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> MaskTypesLoadResult:
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой")
    try:
        return MaskTypesService(db).upsert_from_xlsx(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
