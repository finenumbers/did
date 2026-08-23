"""Twilio raw + catalog + geo sample. Empty incoming never wipes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.twilio import TwilioAvailableNumber, TwilioCatalog, TwilioCountryRaw, TwilioGeo, TwilioPricingRaw
from app.modules.sync_engine.hashing import payload_hash
from app.providers.twilio import contract
from app.providers.twilio.parser import CatalogRow, catalog_key, parse_available_number

FIELD_VERIFICATION = {
    "country": "verified",
    "country_code": "verified",
    "beta": "verified",
    "subresource_uris": "verified",
    "current_price": "verified",
    "price_unit": "verified",
}


class EmptyTwilioFetchError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def persist_twilio_coverage(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    countries: list[dict[str, Any]],
    pricing_by_iso: dict[str, dict[str, Any]],
    rows: list[CatalogRow],
) -> dict[str, int]:
    if not countries:
        previous = (
            db.scalar(
                select(func.count())
                .select_from(TwilioCatalog)
                .where(TwilioCatalog.provider_id == provider_id)
            )
            or 0
        )
        raise EmptyTwilioFetchError(
            f"Twilio returned 0 countries; refusing wipe (catalog has {previous} rows)"
        )
    if not rows:
        previous = (
            db.scalar(
                select(func.count())
                .select_from(TwilioCatalog)
                .where(TwilioCatalog.provider_id == provider_id)
            )
            or 0
        )
        raise EmptyTwilioFetchError(
            f"Twilio returned 0 country×type rows; refusing wipe (catalog has {previous} rows)"
        )

    loaded = datetime.now(timezone.utc)
    db.execute(delete(TwilioPricingRaw))
    db.execute(delete(TwilioCountryRaw))

    for item in countries:
        iso = str(item.get("country_code") or "").strip().upper() or None
        db.add(
            TwilioCountryRaw(
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=item,
                payload_hash=payload_hash(item),
                external_key=iso,
                country_name=str(item.get("country") or "").strip() or None,
                country_iso=iso,
                country_beta=bool(item.get("beta")) if "beta" in item else None,
            )
        )
    for iso, payload in pricing_by_iso.items():
        db.add(
            TwilioPricingRaw(
                sync_job_id=job_id,
                source_loaded_at=loaded,
                raw_payload=payload,
                payload_hash=payload_hash(payload),
                external_key=iso,
                country_iso=iso,
                price_unit=str(payload.get("price_unit") or "").strip() or None,
            )
        )

    seen: set[str] = set()
    stored = 0
    for row in rows:
        key = catalog_key(row.country_iso, row.number_type)
        if key in seen:
            continue
        seen.add(key)
        stmt = pg_insert(TwilioCatalog).values(
            id=uuid.uuid4(),
            provider_id=provider_id,
            provider_group_key=key,
            country_name=row.country_name,
            country_iso=row.country_iso,
            number_type=row.number_type,
            period_price=row.period_price,
            price_unit=row.price_unit,
            country_beta=row.country_beta,
            region_count=0,
            city_count=0,
            field_verification=FIELD_VERIFICATION,
            last_sync_job_id=job_id,
            first_seen_at=loaded,
            last_seen_at=loaded,
            is_currently_present=True,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_twilio_catalog_provider_group",
            set_={
                "country_name": stmt.excluded.country_name,
                "country_iso": stmt.excluded.country_iso,
                "number_type": stmt.excluded.number_type,
                "period_price": stmt.excluded.period_price,
                "price_unit": stmt.excluded.price_unit,
                "country_beta": stmt.excluded.country_beta,
                "region_count": 0,
                "city_count": 0,
                "field_verification": stmt.excluded.field_verification,
                "last_sync_job_id": stmt.excluded.last_sync_job_id,
                "last_seen_at": stmt.excluded.last_seen_at,
                "is_currently_present": True,
                "numbers_synced_at": None,
                "numbers_sync_job_id": None,
                "numbers_sync_geo_job_id": None,
            },
        )
        db.execute(stmt)
        stored += 1

    db.flush()
    return {
        "countries": len(countries),
        "pricing": len(pricing_by_iso),
        "rows": stored,
    }


def ingest_available_batch(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    country_iso: str,
    country_name: str | None,
    number_type: str,
    region_filter: str,
    items: list[dict[str, Any]],
    source: str = contract.NUMBER_SOURCE_GEO,
) -> dict[str, Any]:
    loaded = datetime.now(timezone.utc)
    filter_key = (region_filter or "").strip().upper()
    phones: set[str] = set()
    cities: set[tuple[str, str]] = set()
    regions: set[str] = set()
    had_geo = False

    for item in items:
        parsed = parse_available_number(item)
        if parsed is None:
            continue
        phone = parsed["phone_number"]
        phones.add(phone)
        locality = parsed["locality"]
        region = parsed["region"]
        if locality:
            cities.add((filter_key, locality))
            had_geo = True
        if region:
            regions.add(region)
            had_geo = True
        elif filter_key:
            had_geo = True

        loc_norm = parsed["locality_norm"]
        if locality or region or filter_key:
            geo_stmt = pg_insert(TwilioGeo).values(
                id=uuid.uuid4(),
                provider_id=provider_id,
                country_iso=country_iso,
                number_type=number_type,
                region_filter=filter_key,
                region=region,
                locality=locality,
                locality_norm=loc_norm,
                last_sync_job_id=job_id,
            )
            geo_stmt = geo_stmt.on_conflict_do_update(
                constraint="uq_twilio_geo_cell",
                set_={
                    "region": geo_stmt.excluded.region,
                    "locality": geo_stmt.excluded.locality,
                    "last_sync_job_id": geo_stmt.excluded.last_sync_job_id,
                    "updated_at": loaded,
                },
            )
            db.execute(geo_stmt)

        number_stmt = pg_insert(TwilioAvailableNumber).values(
            id=uuid.uuid4(),
            provider_id=provider_id,
            phone_number=phone,
            country_iso=parsed["country_iso"] or country_iso,
            country_name=country_name,
            number_type=number_type,
            region=region,
            locality=locality,
            address_requirements=parsed["address_requirements"],
            voice=parsed["voice"],
            sms=parsed["sms"],
            mms=parsed["mms"],
            fax=parsed["fax"],
            source=source,
            last_sync_job_id=job_id,
            first_seen_at=loaded,
            last_seen_at=loaded,
        )
        number_stmt = number_stmt.on_conflict_do_update(
            constraint="uq_twilio_available_number",
            set_={
                "country_iso": number_stmt.excluded.country_iso,
                "country_name": number_stmt.excluded.country_name,
                "number_type": number_stmt.excluded.number_type,
                "region": number_stmt.excluded.region,
                "locality": number_stmt.excluded.locality,
                "address_requirements": number_stmt.excluded.address_requirements,
                "voice": number_stmt.excluded.voice,
                "sms": number_stmt.excluded.sms,
                "mms": number_stmt.excluded.mms,
                "fax": number_stmt.excluded.fax,
                "source": number_stmt.excluded.source,
                "last_sync_job_id": number_stmt.excluded.last_sync_job_id,
                "last_seen_at": number_stmt.excluded.last_seen_at,
            },
            where=and_(
                TwilioAvailableNumber.country_iso == country_iso,
                TwilioAvailableNumber.number_type == number_type,
            ),
        )
        db.execute(number_stmt)

    return {
        "phones": phones,
        "cities": cities,
        "regions": regions,
        "had_geo": had_geo,
        "filter_key": filter_key,
    }


def refresh_local_counts(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> tuple[int, int]:
    iso = country_iso.strip().upper()
    if iso in contract.NANP_COUNTRIES:
        region_count = (
            db.scalar(
                select(func.count(func.distinct(TwilioGeo.region_filter))).where(
                    TwilioGeo.provider_id == provider_id,
                    TwilioGeo.country_iso == iso,
                    TwilioGeo.number_type == number_type,
                    TwilioGeo.region_filter != "",
                )
            )
            or 0
        )
    else:
        region_count = (
            db.scalar(
                select(func.count(func.distinct(TwilioGeo.region))).where(
                    TwilioGeo.provider_id == provider_id,
                    TwilioGeo.country_iso == iso,
                    TwilioGeo.number_type == number_type,
                    TwilioGeo.region.is_not(None),
                    TwilioGeo.region != "",
                )
            )
            or 0
        )
    city_count = (
        db.scalar(
            select(func.count()).select_from(
                select(TwilioGeo.region_filter, TwilioGeo.locality)
                .where(
                    TwilioGeo.provider_id == provider_id,
                    TwilioGeo.country_iso == iso,
                    TwilioGeo.number_type == number_type,
                    TwilioGeo.locality.is_not(None),
                    TwilioGeo.locality != "",
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )
    row = db.scalar(
        select(TwilioCatalog).where(
            TwilioCatalog.provider_id == provider_id,
            TwilioCatalog.country_iso == iso,
            TwilioCatalog.number_type == number_type,
        )
    )
    if row is not None:
        row.region_count = int(region_count)
        row.city_count = int(city_count)
    return int(region_count), int(city_count)


def cutover_geo_snapshot(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
) -> dict[str, int]:
    geo_deleted = db.execute(
        delete(TwilioGeo).where(
            TwilioGeo.provider_id == provider_id,
            TwilioGeo.last_sync_job_id.is_distinct_from(job_id),
        )
    ).rowcount
    numbers_deleted = db.execute(
        delete(TwilioAvailableNumber).where(
            TwilioAvailableNumber.provider_id == provider_id,
            TwilioAvailableNumber.source == contract.NUMBER_SOURCE_GEO,
            TwilioAvailableNumber.last_sync_job_id.is_distinct_from(job_id),
        )
    ).rowcount
    catalog_deleted = db.execute(
        delete(TwilioCatalog).where(
            TwilioCatalog.provider_id == provider_id,
            TwilioCatalog.last_sync_job_id.is_distinct_from(job_id),
        )
    ).rowcount
    db.flush()
    return {
        "geo_deleted": int(geo_deleted or 0),
        "numbers_deleted": int(numbers_deleted or 0),
        "catalog_deleted": int(catalog_deleted or 0),
    }


def number_counts_by_type(db: Session, *, provider_id: uuid.UUID) -> dict[tuple[str, str], int]:
    rows = db.execute(
        select(
            TwilioAvailableNumber.country_iso,
            TwilioAvailableNumber.number_type,
            func.count(),
        )
        .where(TwilioAvailableNumber.provider_id == provider_id)
        .group_by(TwilioAvailableNumber.country_iso, TwilioAvailableNumber.number_type)
    ).all()
    return {(str(iso or ""), str(typ or "")): int(cnt) for iso, typ, cnt in rows}


def catalog_progress_rows(db: Session, *, provider_id: uuid.UUID) -> list[dict[str, Any]]:
    counts = number_counts_by_type(db, provider_id=provider_id)
    rows = db.scalars(
        select(TwilioCatalog)
        .where(
            TwilioCatalog.provider_id == provider_id,
            TwilioCatalog.is_currently_present.is_(True),
        )
        .order_by(TwilioCatalog.country_name.asc(), TwilioCatalog.number_type.asc())
    ).all()
    out = []
    for row in rows:
        payload = _catalog_row_payload(row, status="success")
        payload["number_count"] = counts.get((row.country_iso or "", row.number_type or ""), 0)
        out.append(payload)
    return out


def snapshot_totals(db: Session, *, provider_id: uuid.UUID) -> dict[str, int]:
    cities = (
        db.scalar(
            select(func.count()).select_from(
                select(TwilioGeo.country_iso, TwilioGeo.region_filter, TwilioGeo.locality)
                .where(
                    TwilioGeo.provider_id == provider_id,
                    TwilioGeo.locality.is_not(None),
                    TwilioGeo.locality != "",
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )
    numbers = (
        db.scalar(
            select(func.count())
            .select_from(TwilioAvailableNumber)
            .where(TwilioAvailableNumber.provider_id == provider_id)
        )
        or 0
    )
    return {"cities_total": int(cities), "numbers_unique": int(numbers)}


def _catalog_row_payload(row: TwilioCatalog, *, status: str, detail: str = "") -> dict[str, Any]:
    price = row.period_price
    return {
        "country_iso": row.country_iso,
        "country_name": row.country_name,
        "number_type": row.number_type,
        "status": status,
        "detail": detail,
        "region_count": row.region_count,
        "city_count": row.city_count,
        "number_count": 0,
        "period_price": str(price) if isinstance(price, Decimal) else price,
        "price_unit": row.price_unit,
    }


def catalog_numbers_loaded(row: TwilioCatalog) -> bool:
    return bool(
        row.numbers_sync_geo_job_id
        and row.last_sync_job_id
        and row.numbers_sync_geo_job_id == row.last_sync_job_id
    )


def catalog_has_rows(db: Session, *, provider_id: uuid.UUID) -> bool:
    count = (
        db.scalar(
            select(func.count())
            .select_from(TwilioCatalog)
            .where(
                TwilioCatalog.provider_id == provider_id,
                TwilioCatalog.is_currently_present.is_(True),
            )
        )
        or 0
    )
    return int(count) > 0


def load_geo_rows(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> list[TwilioGeo]:
    return list(
        db.scalars(
            select(TwilioGeo).where(
                TwilioGeo.provider_id == provider_id,
                TwilioGeo.country_iso == country_iso,
                TwilioGeo.number_type == number_type,
            )
        ).all()
    )


def get_catalog_row(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> TwilioCatalog | None:
    return db.scalar(
        select(TwilioCatalog).where(
            TwilioCatalog.provider_id == provider_id,
            TwilioCatalog.country_iso == country_iso,
            TwilioCatalog.number_type == number_type,
            TwilioCatalog.is_currently_present.is_(True),
        )
    )


def mark_numbers_synced(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
    job_id: uuid.UUID,
    geo_job_id: uuid.UUID | None,
) -> None:
    row = get_catalog_row(
        db,
        provider_id=provider_id,
        country_iso=country_iso,
        number_type=number_type,
    )
    if row is None:
        return
    row.numbers_synced_at = datetime.now(timezone.utc)
    row.numbers_sync_job_id = job_id
    row.numbers_sync_geo_job_id = geo_job_id or row.last_sync_job_id


def cutover_numbers_row(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> int:
    deleted = db.execute(
        delete(TwilioAvailableNumber).where(
            TwilioAvailableNumber.provider_id == provider_id,
            TwilioAvailableNumber.country_iso == country_iso,
            TwilioAvailableNumber.number_type == number_type,
            TwilioAvailableNumber.last_sync_job_id.is_distinct_from(job_id),
        )
    ).rowcount
    db.flush()
    return int(deleted or 0)
