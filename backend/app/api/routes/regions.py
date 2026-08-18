import tempfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.regions import RegionCityItem, RegionsLoadResult, RegionsSaveRequest
from app.services.regions_service import RegionsService

router = APIRouter(prefix="/regions", tags=["Regions"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "",
    response_model=list[RegionCityItem],
    summary="City and region dictionary (local snapshot from catalog)",
)
def list_regions(db: Session = Depends(get_db)) -> list[RegionCityItem]:
    return RegionsService(db).list_cities()


@router.post(
    "/load",
    response_model=RegionsLoadResult,
    summary="Merge new catalog city/region pairs into the local regions table",
)
def load_regions(db: Session = Depends(get_db)) -> RegionsLoadResult:
    return RegionsService(db).load_from_catalog()


@router.post(
    "/save",
    response_model=RegionsLoadResult,
    summary="Save edited digit capacity values",
)
def save_regions(body: RegionsSaveRequest, db: Session = Depends(get_db)) -> RegionsLoadResult:
    try:
        return RegionsService(db).save_capacities(body.items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/export.xlsx",
    response_class=FileResponse,
    summary="Download Regions table as XLSX (digit capacity, city, region)",
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
