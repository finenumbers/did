from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.regions import RegionCityItem
from app.services.regions_service import RegionsService

router = APIRouter(prefix="/regions", tags=["Regions"])


@router.get(
    "",
    response_model=list[RegionCityItem],
    summary="City and region dictionary (Runexis sync)",
)
def list_regions(db: Session = Depends(get_db)) -> list[RegionCityItem]:
    return RegionsService(db).list_cities()
