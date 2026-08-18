from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.regions import RegionCityItem, RegionsLoadResult
from app.services.regions_service import RegionsService

router = APIRouter(prefix="/regions", tags=["Regions"])


@router.get(
    "",
    response_model=list[RegionCityItem],
    summary="City and region dictionary (local table, SipOut load)",
)
def list_regions(db: Session = Depends(get_db)) -> list[RegionCityItem]:
    return RegionsService(db).list_cities()


@router.post(
    "/load",
    response_model=RegionsLoadResult,
    summary="Replace local regions table from SipOut did/get_cities",
)
async def load_regions(db: Session = Depends(get_db)) -> RegionsLoadResult:
    return await RegionsService(db).load_from_sipout()
