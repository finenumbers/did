from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind
from app.models.regions_directory import RegionsDirectory
from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY
from app.schemas.regions import RegionCityItem, RegionsLoadResult

DIGIT_CAPACITY = 7


def catalog_region_pair(
    city_name: str | None, region_name: str | None
) -> tuple[str, str | None] | None:
    """Return a real city/region pair, or None for blank/sentinel error rows."""
    city = (city_name or "").strip()
    if not city or city == OPERATOR_NOT_IN_REGISTRY:
        return None
    region = (region_name or "").strip() or None
    if region == OPERATOR_NOT_IN_REGISTRY:
        return None
    return city, region


class RegionsService:
    """Local Regions page table. Snapshot from catalog city/region, only via load button."""

    def __init__(self, db: Session):
        self.db = db

    def list_cities(self) -> list[RegionCityItem]:
        rows = self.db.scalars(
            select(RegionsDirectory).order_by(
                RegionsDirectory.region_name.asc().nulls_last(),
                RegionsDirectory.city_name.asc().nulls_last(),
            )
        ).all()
        items: list[RegionCityItem] = []
        for row in rows:
            pair = catalog_region_pair(row.city_name, row.region_name)
            if pair is None:
                continue
            city, region = pair
            items.append(
                RegionCityItem(
                    digit_capacity=DIGIT_CAPACITY,
                    city_name=city,
                    region_name=region,
                )
            )
        return items

    def load_from_catalog(self) -> RegionsLoadResult:
        city_expr = func.btrim(NumbersCatalogNormalized.city_name)
        region_expr = func.nullif(func.btrim(NumbersCatalogNormalized.region_name), "")
        stmt = (
            select(city_expr, region_expr)
            .where(NumbersCatalogNormalized.is_currently_present.is_(True))
            .where(
                NumbersCatalogNormalized.inventory_kind.in_(
                    (InventoryKind.free, InventoryKind.purchased)
                )
            )
            .where(NumbersCatalogNormalized.city_name.is_not(None))
            .where(city_expr != "")
            .where(city_expr != OPERATOR_NOT_IN_REGISTRY)
            .where(
                or_(
                    NumbersCatalogNormalized.region_name.is_(None),
                    func.btrim(NumbersCatalogNormalized.region_name) == "",
                    region_expr != OPERATOR_NOT_IN_REGISTRY,
                )
            )
            .distinct()
        )
        mapped: list[tuple[str, str | None]] = []
        seen: set[tuple[str, str]] = set()
        for city_raw, region_raw in self.db.execute(stmt).all():
            pair = catalog_region_pair(city_raw, region_raw)
            if pair is None:
                continue
            city, region = pair
            key = (city, region or "")
            if key in seen:
                continue
            seen.add(key)
            mapped.append((city, region))
        loaded_at = datetime.now(timezone.utc)
        self.db.execute(delete(RegionsDirectory))
        self.db.add_all(
            [
                RegionsDirectory(
                    city_name=city,
                    region_name=region,
                    loaded_at=loaded_at,
                )
                for city, region in mapped
            ]
        )
        self.db.commit()
        return RegionsLoadResult(
            ok=True,
            count=len(mapped),
            message=f"Загружено комбинаций: {len(mapped)}",
        )
