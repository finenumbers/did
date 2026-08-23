"""Replace DIDWW raw + catalog in one transaction. Empty incoming never wipes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.didww import (
    DidwwCatalog,
    DidwwCityRaw,
    DidwwCountryRaw,
    DidwwDidGroupRaw,
    DidwwDidGroupTypeRaw,
    DidwwRegionRaw,
)
from app.modules.sync_engine.hashing import payload_hash
from app.providers.didww.parser import DidGroupRow, pick_display_sku


FIELD_VERIFICATION = {
    "setup_price": "verified",
    "monthly_price": "verified",
    "channels_included_count": "verified",
    "iso": "verified",
    "is_available": "verified",
    "total_count": "verified",
    "available_dids_enabled": "verified",
    "needs_registration": "verified",
    "stock_keeping_units": "verified",
}


class EmptyDidwwFetchError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def persist_didww_coverage(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    countries: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    cities: list[dict[str, Any]],
    group_types: list[dict[str, Any]],
    groups: list[DidGroupRow],
) -> dict[str, int]:
    if not groups:
        previous = (
            db.scalar(
                select(func.count())
                .select_from(DidwwCatalog)
                .where(DidwwCatalog.provider_id == provider_id)
            )
            or 0
        )
        raise EmptyDidwwFetchError(
            f"DIDWW returned 0 DID Groups; refusing wipe (catalog has {previous} rows)"
        )

    loaded = datetime.now(timezone.utc)
    # Rows are replaced wholesale, so carry first_seen_at over for groups we already knew.
    first_seen_by_key: dict[str, datetime] = dict(
        db.execute(
            select(DidwwCatalog.provider_group_key, DidwwCatalog.first_seen_at).where(
                DidwwCatalog.provider_id == provider_id
            )
        ).all()
    )
    db.execute(delete(DidwwCatalog).where(DidwwCatalog.provider_id == provider_id))
    db.execute(delete(DidwwDidGroupRaw))
    db.execute(delete(DidwwDidGroupTypeRaw))
    db.execute(delete(DidwwCityRaw))
    db.execute(delete(DidwwRegionRaw))
    db.execute(delete(DidwwCountryRaw))

    for item in countries:
        attrs = item.get("attributes") or {}
        db.add(
            DidwwCountryRaw(
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=item,
                payload_hash=payload_hash(item),
                external_key=str(item.get("id") or "") or None,
                name=attrs.get("name"),
                iso=attrs.get("iso"),
                prefix=attrs.get("prefix"),
            )
        )
    for item in regions:
        attrs = item.get("attributes") or {}
        country = ((item.get("relationships") or {}).get("country") or {}).get("data") or {}
        db.add(
            DidwwRegionRaw(
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=item,
                payload_hash=payload_hash(item),
                external_key=str(item.get("id") or "") or None,
                name=attrs.get("name"),
                country_external_id=str(country.get("id") or "") or None,
                iso=attrs.get("iso"),
            )
        )
    for item in cities:
        attrs = item.get("attributes") or {}
        rels = item.get("relationships") or {}
        country = (rels.get("country") or {}).get("data") or {}
        region = (rels.get("region") or {}).get("data") or {}
        db.add(
            DidwwCityRaw(
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=item,
                payload_hash=payload_hash(item),
                external_key=str(item.get("id") or "") or None,
                name=attrs.get("name"),
                country_external_id=str(country.get("id") or "") or None,
                region_external_id=str(region.get("id") or "") or None,
            )
        )
    for item in group_types:
        attrs = item.get("attributes") or {}
        db.add(
            DidwwDidGroupTypeRaw(
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=item,
                payload_hash=payload_hash(item),
                external_key=str(item.get("id") or "") or None,
                name=attrs.get("name"),
            )
        )

    seen: set[str] = set()
    stored = 0
    for group in groups:
        if not group.group_id or group.group_id in seen:
            continue
        seen.add(group.group_id)
        raw_id = uuid.uuid4()
        db.add(
            DidwwDidGroupRaw(
                id=raw_id,
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=group.raw,
                payload_hash=payload_hash(group.raw),
                external_key=group.group_id,
                prefix=group.prefix,
                area_name=group.area_name,
                country_iso=group.country_iso,
            )
        )
        sku = pick_display_sku(group.skus)
        skus_json = [
            {
                "id": s.sku_id,
                "setup_price": str(s.setup_price) if s.setup_price is not None else None,
                "monthly_price": str(s.monthly_price) if s.monthly_price is not None else None,
                "channels_included": s.channels_included,
            }
            for s in group.skus
        ]
        db.add(
            DidwwCatalog(
                provider_id=provider_id,
                provider_group_key=group.group_id,
                country_name=group.country_name,
                country_iso=group.country_iso,
                country_prefix=group.country_prefix,
                region_name=group.region_name,
                city_name=group.city_name or group.area_name,
                area_prefix=group.prefix,
                did_type=group.did_type,
                buy_price=sku.setup_price if sku else None,
                period_price=sku.monthly_price if sku else None,
                channels_included=sku.channels_included if sku else None,
                stock_count=group.stock_count,
                number_select=group.number_select,
                features=", ".join(group.features) if group.features else None,
                needs_registration=group.needs_registration,
                is_metered=group.is_metered,
                skus_json={"skus": skus_json},
                field_verification=FIELD_VERIFICATION,
                raw_source_id=raw_id,
                last_sync_job_id=job_id,
                first_seen_at=first_seen_by_key.get(group.group_id, loaded),
                last_seen_at=loaded,
                is_currently_present=True,
            )
        )
        stored += 1

    db.flush()
    return {
        "countries": len(countries),
        "regions": len(regions),
        "cities": len(cities),
        "did_group_types": len(group_types),
        "groups": stored,
    }
