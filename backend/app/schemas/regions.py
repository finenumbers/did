from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

from app.providers.msisdn_split import DIGIT_CAPACITY_DEFAULT, DIGIT_CAPACITY_MAX, DIGIT_CAPACITY_MIN


class RegionCityItem(BaseModel):
    """City/region row for the Regions page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    digit_capacity: int = DIGIT_CAPACITY_DEFAULT
    city_name: str
    region_name: str | None = None


class RegionsLoadResult(BaseModel):
    ok: bool = True
    count: int
    message: str


class RegionCapacitySaveItem(BaseModel):
    id: UUID
    digit_capacity: int = Field(ge=DIGIT_CAPACITY_MIN, le=DIGIT_CAPACITY_MAX)


class RegionsSaveRequest(BaseModel):
    items: list[RegionCapacitySaveItem]
