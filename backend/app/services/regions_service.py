from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import ProviderCode
from app.models.providers import Provider
from app.models.regions_directory import RegionsDirectory
from app.providers.dto.common import ConnectionConfig
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.errors import ProviderError
from app.providers.sipout.client import SipOutClient
from app.providers.sipout.parser import parse_geo
from app.schemas.regions import RegionCityItem, RegionsLoadResult


@dataclass(frozen=True, slots=True)
class DirectoryRow:
    city_name: str
    region_name: str | None
    city_external_id: str | None
    region_external_id: str | None


def directory_rows_from_sipout(
    regions: list[ParsedRegion],
    cities: list[ParsedCity],
) -> list[DirectoryRow]:
    """Join SipOut cities to region names by region_id. ABC is not in get_cities."""
    region_names: dict[str, str] = {}
    for region in regions:
        rid = (region.region_external_id or "").strip()
        name = (region.name or "").strip()
        if rid and name:
            region_names[rid] = name
    rows: list[DirectoryRow] = []
    for city in cities:
        city_name = (city.name or "").strip()
        if not city_name:
            continue
        rid = (city.region_external_id or "").strip() or None
        rows.append(
            DirectoryRow(
                city_name=city_name,
                region_name=region_names.get(rid) if rid else None,
                city_external_id=(city.city_external_id or "").strip() or None,
                region_external_id=rid,
            )
        )
    return rows


class RegionsService:
    """Local Regions page table. Source: SipOut `did/get_cities`, only via load button."""

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
            city = (row.city_name or "").strip()
            if not city:
                continue
            region = (row.region_name or "").strip() or None
            items.append(RegionCityItem(abc=None, city_name=city, region_name=region))
        return items

    async def load_from_sipout(self) -> RegionsLoadResult:
        provider = self.db.scalar(
            select(Provider)
            .where(Provider.code == ProviderCode.sipout)
            .options(joinedload(Provider.connection))
        )
        if not provider:
            raise ProviderError("Провайдер SipOut не найден", code="SIPOUT_NOT_FOUND")
        conn = provider.connection
        if not conn:
            raise ProviderError("Нет настроек подключения SipOut", code="SIPOUT_NOT_CONFIGURED")
        cfg = ConnectionConfig(
            base_url=conn.base_url,
            auth_settings=dict(conn.auth_settings or {}),
            extra_settings=conn.extra_settings or {},
        )
        raw = await SipOutClient(cfg).get_cities()
        regions, cities = parse_geo(raw)
        mapped = directory_rows_from_sipout(regions, cities)
        loaded_at = datetime.now(timezone.utc)
        self.db.execute(delete(RegionsDirectory))
        self.db.add_all(
            [
                RegionsDirectory(
                    abc=None,
                    city_name=row.city_name,
                    region_name=row.region_name,
                    city_external_id=row.city_external_id,
                    region_external_id=row.region_external_id,
                    loaded_at=loaded_at,
                )
                for row in mapped
            ]
        )
        self.db.commit()
        return RegionsLoadResult(
            ok=True,
            count=len(mapped),
            message=f"Загружено городов: {len(mapped)}",
        )
