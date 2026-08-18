import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.mask_types import MaskTypeItem, MaskTypesLoadResult
from app.services.mask_types_service import MAX_IMPORT_BYTES, MaskTypesService

router = APIRouter(prefix="/mask-types", tags=["Mask types"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "",
    response_model=list[MaskTypeItem],
    summary="Mask types directory",
)
def list_mask_types(db: Session = Depends(get_db)) -> list[MaskTypeItem]:
    return MaskTypesService(db).list_items()


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
