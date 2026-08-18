from pydantic import BaseModel, ConfigDict


class RegionCityItem(BaseModel):
    """City/region row for the Regions page. Digit capacity is a presentation constant."""

    model_config = ConfigDict(from_attributes=True)

    digit_capacity: int = 7
    city_name: str
    region_name: str | None = None


class RegionsLoadResult(BaseModel):
    ok: bool = True
    count: int
    message: str
