from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind
from app.models.regions_directory import RegionsDirectory
from app.modules.catalog.gar_territory import is_coverage_value
from app.providers.finenumbers.contract import OPERATOR_NOT_IN_REGISTRY
from app.providers.msisdn_split import DIGIT_CAPACITY_DEFAULT
from app.schemas.regions import RegionCapacitySaveItem, RegionCityItem, RegionsLoadResult
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook

REGIONS_XLSX_HEADERS = ("Разрядность", "Город", "Регион")
REGIONS_XLSX_SHEET = "Регионы"

DIGIT_CAPACITY = DIGIT_CAPACITY_DEFAULT


def catalog_region_pair(
    city_name: str | None, region_name: str | None
) -> tuple[str, str | None] | None:
    """Return a real city/region pair, or None for blank/sentinel error rows."""
    city = (city_name or "").strip()
    if not city or city == OPERATOR_NOT_IN_REGISTRY:
        return None
    if is_coverage_value(city):
        return None
    region = (region_name or "").strip() or None
    if region == OPERATOR_NOT_IN_REGISTRY:
        return None
    if is_coverage_value(region):
        region = None
    return city, region


class RegionsService:
    """Local Regions page table. Snapshot from catalog city/region, only via load/save buttons."""

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
            cap = int(row.digit_capacity) if row.digit_capacity else DIGIT_CAPACITY_DEFAULT
            items.append(
                RegionCityItem(
                    id=row.id,
                    digit_capacity=cap,
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
        wanted = {(city, region or "") for city, region in mapped}

        existing_rows = list(self.db.scalars(select(RegionsDirectory)).all())
        existing_by_key: dict[tuple[str, str], RegionsDirectory] = {}
        to_delete: list[RegionsDirectory] = []
        for row in existing_rows:
            pair = catalog_region_pair(row.city_name, row.region_name)
            if pair is None:
                to_delete.append(row)
                continue
            key = (pair[0], pair[1] or "")
            if key not in wanted:
                to_delete.append(row)
                continue
            existing_by_key[key] = row

        loaded_at = datetime.now(timezone.utc)
        to_add: list[RegionsDirectory] = []
        for city, region in mapped:
            key = (city, region or "")
            if key in existing_by_key:
                continue
            to_add.append(
                RegionsDirectory(
                    city_name=city,
                    region_name=region,
                    digit_capacity=DIGIT_CAPACITY_DEFAULT,
                    loaded_at=loaded_at,
                )
            )
        for row in to_delete:
            self.db.delete(row)
        if to_add:
            self.db.add_all(to_add)
        self.db.commit()
        return RegionsLoadResult(
            ok=True,
            count=len(to_add),
            message=f"Добавлено комбинаций: {len(to_add)}, удалено: {len(to_delete)}",
        )

    def save_capacities(self, items: list[RegionCapacitySaveItem]) -> RegionsLoadResult:
        if not items:
            return RegionsLoadResult(ok=True, count=0, message="Нет изменений")
        by_id: dict[UUID, int] = {}
        for item in items:
            by_id[item.id] = item.digit_capacity
        rows = self.db.scalars(
            select(RegionsDirectory).where(RegionsDirectory.id.in_(by_id.keys()))
        ).all()
        found = {row.id for row in rows}
        missing = set(by_id) - found
        if missing:
            raise ValueError("Строка регионов не найдена")
        for row in rows:
            row.digit_capacity = by_id[row.id]
        self.db.commit()
        return RegionsLoadResult(
            ok=True,
            count=len(rows),
            message=f"Сохранено: {len(rows)}",
        )

    def write_xlsx(self, path: str | Path) -> int:
        """Write the Regions table (same columns as the UI) to path."""
        items = self.list_cities()
        wb = open_styled_workbook(str(path), constant_memory=True)
        try:
            ws = wb.add_worksheet(REGIONS_XLSX_SHEET)
            writer = StyledSheetWriter(wb, ws, REGIONS_XLSX_HEADERS)
            for item in items:
                writer.write_row(
                    [item.digit_capacity, item.city_name, item.region_name or ""]
                )
            writer.finalize()
        finally:
            wb.close()
        return len(items)
