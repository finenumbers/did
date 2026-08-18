from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.providers.msisdn_split import DIGIT_CAPACITY_DEFAULT


class RegionCityItem(BaseModel):
    """Row for the Regions page (ABC, capacity, city, region)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    abc: str
    digit_capacity: int = DIGIT_CAPACITY_DEFAULT
    city_name: str
    region_name: str | None = None


class RegionsLoadResult(BaseModel):
    ok: bool = True
    count: int
    message: str
