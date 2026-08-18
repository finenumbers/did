"""Apply saved Regions digit capacity to catalog ABC + local after geo/RTU."""

from __future__ import annotations

import uuid

from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from app.models.catalog import NumbersCatalogNormalized
from app.models.regions_directory import RegionsDirectory
from app.providers.msisdn_split import (
    DIGIT_CAPACITY_MAX,
    DIGIT_CAPACITY_MIN,
    split_msisdn_by_capacity,
)
from app.services.regions_service import catalog_region_pair


def capacity_lookup(
    rows: list[RegionsDirectory],
) -> dict[tuple[str, str], int]:
    lookup: dict[tuple[str, str], int] = {}
    for row in rows:
        pair = catalog_region_pair(row.city_name, row.region_name)
        if pair is None:
            continue
        cap = int(row.digit_capacity) if row.digit_capacity is not None else 0
        if cap < DIGIT_CAPACITY_MIN or cap > DIGIT_CAPACITY_MAX:
            continue
        city, region = pair
        lookup[(city, region or "")] = cap
    return lookup


def abc_local_updates(
    lookup: dict[tuple[str, str], int],
    rows: list[tuple[uuid.UUID, str | None, str | None, str | None, str | None, str | None]],
) -> list[tuple[uuid.UUID, str, str]]:
    """id, msisdn, city, region, current_abc, current_local → updates that actually change."""
    out: list[tuple[uuid.UUID, str, str]] = []
    for catalog_id, msisdn, city_name, region_name, current_abc, current_local in rows:
        pair = catalog_region_pair(city_name, region_name)
        if pair is None:
            continue
        city, region = pair
        cap = lookup.get((city, region or ""))
        if cap is None:
            continue
        parts = split_msisdn_by_capacity(msisdn, cap)
        if parts is None:
            continue
        abc, local = parts
        if current_abc == abc and current_local == local:
            continue
        out.append((catalog_id, abc, local))
    return out


def apply_catalog_abc_from_regions(db: Session) -> dict[str, int]:
    """Rewrite catalog abc_code/number_local from saved region capacities. Does not change category."""
    lookup = capacity_lookup(list(db.scalars(select(RegionsDirectory)).all()))
    if not lookup:
        return {"scanned": 0, "updated": 0}
    catalog_rows = db.execute(
        select(
            NumbersCatalogNormalized.id,
            NumbersCatalogNormalized.msisdn,
            NumbersCatalogNormalized.city_name,
            NumbersCatalogNormalized.region_name,
            NumbersCatalogNormalized.abc_code,
            NumbersCatalogNormalized.number_local,
        ).where(NumbersCatalogNormalized.is_currently_present.is_(True))
    ).all()
    updates = abc_local_updates(lookup, list(catalog_rows))
    if not updates:
        return {"scanned": len(catalog_rows), "updated": 0}
    stmt = (
        update(NumbersCatalogNormalized)
        .where(NumbersCatalogNormalized.id == bindparam("b_id"))
        .values(abc_code=bindparam("b_abc"), number_local=bindparam("b_local"))
    )
    db.execute(
        stmt.execution_options(synchronize_session=False),
        [{"b_id": catalog_id, "b_abc": abc, "b_local": local} for catalog_id, abc, local in updates],
    )
    return {"scanned": len(catalog_rows), "updated": len(updates)}
