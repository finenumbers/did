"""Dump complete catalog geo + unusual PSTN GAR into the sync debug log."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind
from app.models.pstn_cache import PstnInnRangeCache
from app.modules.sync_engine.run_file_log import dump_json, get_sync_debug_log


def is_unusual_gar_territory(gar_territory: str | None) -> bool:
    """True when GAR is a coverage blob: no pipe, or more than two commas."""
    text = (gar_territory or "").strip()
    if not text:
        return False
    return "|" not in text or text.count(",") > 2


def dump_sync_geo_diagnostics(db: Session) -> None:
    """Write every distinct catalog geo pair and unusual cache GAR rows, untruncated."""
    fl = get_sync_debug_log()
    if fl is None:
        return

    geo_stmt = (
        select(
            NumbersCatalogNormalized.city_name,
            NumbersCatalogNormalized.region_name,
            func.count().label("n"),
        )
        .where(NumbersCatalogNormalized.is_currently_present.is_(True))
        .where(
            NumbersCatalogNormalized.inventory_kind.in_(
                (InventoryKind.free, InventoryKind.purchased)
            )
        )
        .group_by(
            NumbersCatalogNormalized.city_name,
            NumbersCatalogNormalized.region_name,
        )
        .order_by(func.count().desc())
    )
    geo_rows = db.execute(geo_stmt).all()
    fl.write("INFO", f"=== CATALOG GEO DISTINCT count={len(geo_rows)} ===")
    for city, region, n in geo_rows:
        fl.write(
            "INFO",
            "catalog_geo "
            + dump_json({"count": int(n), "city_name": city, "region_name": region}),
        )

    gt = PstnInnRangeCache.gar_territory
    comma_count = func.length(gt) - func.length(func.replace(gt, ",", ""))
    gar_stmt = (
        select(PstnInnRangeCache)
        .where(gt.is_not(None))
        .where(gt != "")
        .where(or_(~gt.contains("|"), comma_count > 2))
        .order_by(PstnInnRangeCache.operator, PstnInnRangeCache.abc, PstnInnRangeCache.range_start)
    )
    gar_rows = db.scalars(gar_stmt).all()
    unusual = [row for row in gar_rows if is_unusual_gar_territory(row.gar_territory)]
    fl.write("INFO", f"=== UNUSUAL PSTN GAR count={len(unusual)} ===")
    for row in unusual:
        fl.write(
            "INFO",
            "pstn_gar "
            + dump_json(
                {
                    "operator": row.operator,
                    "abc": row.abc,
                    "range_start": row.range_start,
                    "range_end": row.range_end,
                    "gar_territory": row.gar_territory,
                }
            ),
        )
