"""Persist phase: raw upsert + catalog normalize + history. OPERATIONAL soft-absence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import NumberPriceHistory, NumbersCatalogNormalized, NumberStatusHistory
from app.models.enums import HistoryChangeSource, InventoryKind, MappingConfidence
from app.models.runexis_raw import RunexisCityRaw, RunexisRegionRaw
from app.models.sipout_raw import (
    SipoutCityRaw,
    SipoutFreeNumberRaw,
    SipoutPurchasedNumberRaw,
    SipoutRegionRaw,
)
from app.modules.sync_engine.hashing import payload_hash
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import NormalizedNumber


def _now() -> datetime:
    return datetime.now(timezone.utc)


def persist_regions(
    db: Session,
    *,
    provider_code: str,
    job_id: uuid.UUID,
    regions: list[ParsedRegion],
) -> int:
    count = 0
    loaded = _now()
    for region in regions:
        key = region.region_external_id
        ph = payload_hash(region.raw_payload)
        model_cls = SipoutRegionRaw if provider_code == "sipout" else RunexisRegionRaw
        row = None
        if key:
            row = db.scalar(select(model_cls).where(model_cls.external_key == key))
        if row and row.payload_hash == ph:
            row.source_loaded_at = loaded
            row.sync_job_id = job_id
        elif row:
            row.raw_payload = region.raw_payload
            row.payload_hash = ph
            row.source_loaded_at = loaded
            row.sync_job_id = job_id
            row.region_external_id = region.region_external_id
            row.name = region.name
            if isinstance(row, SipoutRegionRaw):
                row.eng_name = region.eng_name
                row.capital_city = region.capital_city
                row.gmt = region.gmt
        else:
            kwargs: dict[str, Any] = {
                "sync_job_id": job_id,
                "source_loaded_at": loaded,
                "raw_payload": region.raw_payload,
                "payload_hash": ph,
                "external_key": key,
                "region_external_id": region.region_external_id,
                "name": region.name,
            }
            if provider_code == "sipout":
                kwargs.update(
                    eng_name=region.eng_name,
                    capital_city=region.capital_city,
                    gmt=region.gmt,
                )
            db.add(model_cls(**kwargs))
        count += 1
    db.flush()
    return count


def persist_cities(
    db: Session,
    *,
    provider_code: str,
    job_id: uuid.UUID,
    cities: list[ParsedCity],
) -> int:
    count = 0
    loaded = _now()
    for city in cities:
        key = city.city_external_id
        ph = payload_hash(city.raw_payload)
        model_cls = SipoutCityRaw if provider_code == "sipout" else RunexisCityRaw
        row = None
        if key:
            row = db.scalar(select(model_cls).where(model_cls.external_key == key))
        if row and row.payload_hash == ph:
            row.source_loaded_at = loaded
            row.sync_job_id = job_id
        elif row:
            row.raw_payload = city.raw_payload
            row.payload_hash = ph
            row.source_loaded_at = loaded
            row.sync_job_id = job_id
            row.city_external_id = city.city_external_id
            if isinstance(row, SipoutCityRaw):
                row.name = city.name
                row.eng_name = city.eng_name
                row.region_external_id = city.region_external_id
            else:
                row.city_name = city.name
                row.region_external_id = city.region_external_id
                row.region_name = city.region_name
        else:
            if provider_code == "sipout":
                db.add(
                    SipoutCityRaw(
                        sync_job_id=job_id,
                        source_loaded_at=loaded,
                        raw_payload=city.raw_payload,
                        payload_hash=ph,
                        external_key=key,
                        city_external_id=city.city_external_id,
                        name=city.name,
                        eng_name=city.eng_name,
                        region_external_id=city.region_external_id,
                    )
                )
            else:
                db.add(
                    RunexisCityRaw(
                        sync_job_id=job_id,
                        source_loaded_at=loaded,
                        raw_payload=city.raw_payload,
                        payload_hash=ph,
                        external_key=key,
                        city_external_id=city.city_external_id,
                        city_name=city.name,
                        region_external_id=city.region_external_id,
                        region_name=city.region_name,
                    )
                )
        count += 1
    db.flush()
    return count


def persist_sipout_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    soft_absence: bool = True,
) -> dict[str, int]:
    loaded = _now()
    seen_keys: set[str] = set()
    upserted = 0
    history_price = 0
    history_status = 0

    for num in numbers:
        seen_keys.add(num.provider_number_key)
        ph = payload_hash(num.raw_payload)
        if inventory_kind == InventoryKind.free:
            raw_cls = SipoutFreeNumberRaw
            raw_row = db.scalar(
                select(SipoutFreeNumberRaw).where(
                    SipoutFreeNumberRaw.external_key == num.provider_number_key
                )
            )
            if raw_row is None:
                raw_row = SipoutFreeNumberRaw(
                    sync_job_id=job_id,
                    source_loaded_at=loaded,
                    raw_payload=num.raw_payload,
                    payload_hash=ph,
                    external_key=num.provider_number_key,
                    did=num.provider_number_key,
                    price=str(num.price_amount) if num.price_amount is not None else None,
                    city_id=num.city_external_id,
                )
                db.add(raw_row)
                db.flush()
            else:
                raw_row.sync_job_id = job_id
                raw_row.source_loaded_at = loaded
                if raw_row.payload_hash != ph:
                    raw_row.raw_payload = num.raw_payload
                    raw_row.payload_hash = ph
                    raw_row.price = str(num.price_amount) if num.price_amount is not None else None
                    raw_row.city_id = num.city_external_id
        else:
            raw_row = db.scalar(
                select(SipoutPurchasedNumberRaw).where(
                    SipoutPurchasedNumberRaw.external_key == num.provider_number_key
                )
            )
            if raw_row is None:
                raw_row = SipoutPurchasedNumberRaw(
                    sync_job_id=job_id,
                    source_loaded_at=loaded,
                    raw_payload=num.raw_payload,
                    payload_hash=ph,
                    external_key=num.provider_number_key,
                    did=num.provider_number_key,
                    status=num.status_raw,
                    city_id=num.city_external_id,
                    has_sms=str(num.raw_payload.get("has_sms"))
                    if num.raw_payload.get("has_sms") is not None
                    else None,
                    user_comment=str(num.raw_payload.get("user_comment"))
                    if num.raw_payload.get("user_comment") is not None
                    else None,
                    order_id=str(num.raw_payload.get("order_id"))
                    if num.raw_payload.get("order_id") is not None
                    else None,
                    doc_status=str(num.raw_payload.get("doc_status"))
                    if num.raw_payload.get("doc_status") is not None
                    else None,
                    sign=str(num.raw_payload.get("sign"))
                    if num.raw_payload.get("sign") is not None
                    else None,
                )
                db.add(raw_row)
                db.flush()
            else:
                raw_row.sync_job_id = job_id
                raw_row.source_loaded_at = loaded
                if raw_row.payload_hash != ph:
                    raw_row.raw_payload = num.raw_payload
                    raw_row.payload_hash = ph
                    raw_row.status = num.status_raw
                    raw_row.city_id = num.city_external_id

        catalog = db.scalar(
            select(NumbersCatalogNormalized).where(
                NumbersCatalogNormalized.provider_id == provider_id,
                NumbersCatalogNormalized.inventory_kind == inventory_kind,
                NumbersCatalogNormalized.provider_number_key == num.provider_number_key,
            )
        )
        table_name = (
            "sipout_free_numbers_raw"
            if inventory_kind == InventoryKind.free
            else "sipout_purchased_numbers_raw"
        )
        if catalog is None:
            catalog = NumbersCatalogNormalized(
                provider_id=provider_id,
                inventory_kind=inventory_kind,
                provider_number_key=num.provider_number_key,
                msisdn=num.msisdn,
                region_external_id=num.region_external_id,
                city_external_id=num.city_external_id,
                region_name=num.region_name,
                city_name=num.city_name,
                price_amount=num.price_amount,
                price_currency=num.price_currency,
                status_raw=num.status_raw,
                has_sms=num.has_sms,
                tariff_name=num.tariff_name,
                raw_source_table=table_name,
                raw_source_id=raw_row.id,
                last_sync_job_id=job_id,
                field_verification=num.field_verification,
                mapping_confidence=num.mapping_confidence,
                first_seen_at=loaded,
                last_seen_at=loaded,
                is_currently_present=True,
                normalized_payload=num.normalized_payload,
            )
            db.add(catalog)
            upserted += 1
        else:
            old_price = catalog.price_amount
            old_status = catalog.status_raw
            catalog.msisdn = num.msisdn
            catalog.region_external_id = num.region_external_id
            catalog.city_external_id = num.city_external_id
            catalog.region_name = num.region_name
            catalog.city_name = num.city_name
            catalog.price_amount = num.price_amount
            catalog.status_raw = num.status_raw
            catalog.has_sms = num.has_sms
            catalog.tariff_name = num.tariff_name
            catalog.raw_source_table = table_name
            catalog.raw_source_id = raw_row.id
            catalog.last_sync_job_id = job_id
            catalog.field_verification = num.field_verification
            catalog.mapping_confidence = num.mapping_confidence
            catalog.last_seen_at = loaded
            catalog.is_currently_present = True
            catalog.normalized_payload = num.normalized_payload
            upserted += 1

            # History only when mapped fields present (example_confirmed allowed conservatively)
            if num.price_amount is not None and old_price != num.price_amount:
                if num.field_verification.get("price_amount") in {
                    "example_confirmed",
                    "documentation_verified",
                }:
                    db.add(
                        NumberPriceHistory(
                            catalog_id=catalog.id,
                            old_price=old_price,
                            new_price=num.price_amount,
                            observed_at=loaded,
                            sync_job_id=job_id,
                            change_source=HistoryChangeSource.sync,
                            raw_source_table=table_name,
                            raw_source_id=raw_row.id,
                            meta={"verification": num.field_verification.get("price_amount")},
                        )
                    )
                    history_price += 1
            if num.status_raw is not None and old_status != num.status_raw:
                if num.field_verification.get("status_raw") in {
                    "example_confirmed",
                    "documentation_verified",
                }:
                    db.add(
                        NumberStatusHistory(
                            catalog_id=catalog.id,
                            old_status_raw=old_status,
                            new_status_raw=num.status_raw,
                            observed_at=loaded,
                            sync_job_id=job_id,
                            change_source=HistoryChangeSource.sync,
                            raw_source_table=table_name,
                            raw_source_id=raw_row.id,
                            meta={"verification": num.field_verification.get("status_raw")},
                        )
                    )
                    history_status += 1

    marked_absent = 0
    if soft_absence:
        existing = db.scalars(
            select(NumbersCatalogNormalized).where(
                NumbersCatalogNormalized.provider_id == provider_id,
                NumbersCatalogNormalized.inventory_kind == inventory_kind,
                NumbersCatalogNormalized.is_currently_present.is_(True),
            )
        ).all()
        for cat in existing:
            if cat.provider_number_key not in seen_keys:
                cat.is_currently_present = False
                cat.last_sync_job_id = job_id
                marked_absent += 1

    db.flush()
    return {
        "upserted": upserted,
        "marked_absent": marked_absent,
        "price_history": history_price,
        "status_history": history_status,
    }


def build_city_lookup(db: Session, provider_code: str) -> dict[str, tuple[str | None, str | None, str | None]]:
    """city_id -> (city_name, region_external_id, region_name)."""
    lookup: dict[str, tuple[str | None, str | None, str | None]] = {}
    if provider_code == "sipout":
        cities = db.scalars(select(SipoutCityRaw)).all()
        regions = {
            r.region_external_id: r.name
            for r in db.scalars(select(SipoutRegionRaw)).all()
            if r.region_external_id
        }
        for c in cities:
            if not c.city_external_id:
                continue
            lookup[c.city_external_id] = (
                c.name,
                c.region_external_id,
                regions.get(c.region_external_id) if c.region_external_id else None,
            )
    else:
        cities = db.scalars(select(RunexisCityRaw)).all()
        for c in cities:
            if not c.city_external_id:
                continue
            lookup[c.city_external_id] = (c.city_name, c.region_external_id, c.region_name)
    return lookup
