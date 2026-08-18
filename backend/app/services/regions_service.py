from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.runexis_raw import RunexisCityRaw
from app.schemas.regions import RegionCityItem


class RegionsService:
    """City/region dictionary from synced Runexis `GET api/v1/regions/cities`."""

    def __init__(self, db: Session):
        self.db = db

    def list_cities(self) -> list[RegionCityItem]:
        rows = self.db.scalars(
            select(RunexisCityRaw).order_by(
                RunexisCityRaw.region_name.asc().nulls_last(),
                RunexisCityRaw.city_name.asc().nulls_last(),
            )
        ).all()
        items: list[RegionCityItem] = []
        for row in rows:
            city = (row.city_name or "").strip()
            if not city:
                continue
            region = (row.region_name or "").strip() or None
            items.append(RegionCityItem(abc=None, city_name=city, region_name=region))
        return items
