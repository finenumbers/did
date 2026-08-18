from pydantic import BaseModel, ConfigDict


class RegionCityItem(BaseModel):
    """City/region row for the Regions page. `abc` is reserved and left empty for now."""

    model_config = ConfigDict(from_attributes=True)

    abc: str | None = None
    city_name: str
    region_name: str | None = None
