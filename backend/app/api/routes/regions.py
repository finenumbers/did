import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.regions import RegionCityItem, RegionsLoadResult
from app.services.regions_service import MAX_IMPORT_BYTES, RegionsService

router = APIRouter(prefix="/regions", tags=["Regions"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "",
    response_model=list[RegionCityItem],
    summary="Regions directory (ABC, digit capacity, city, region)",
)
def list_regions(db: Session = Depends(get_db)) -> list[RegionCityItem]:
    return RegionsService(db).list_cities()


@router.get(
    "/export.xlsx",
    response_class=FileResponse,
    summary="Download Regions table as XLSX",
)
def export_regions_xlsx(db: Session = Depends(get_db)) -> FileResponse:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    RegionsService(db).write_xlsx(tmp.name)
    return FileResponse(
        tmp.name,
        media_type=_XLSX_MEDIA,
        filename="regions.xlsx",
    )


@router.post(
    "/import.xlsx",
    response_model=RegionsLoadResult,
    summary="Replace Regions table from XLSX (full replace)",
)
async def import_regions_xlsx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RegionsLoadResult:
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой")
    try:
        return RegionsService(db).replace_from_xlsx(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
