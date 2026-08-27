"""Twilio raw + catalog + geo sample. Empty incoming never wipes."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.twilio import TwilioAvailableNumber, TwilioCatalog, TwilioCountryRaw, TwilioGeo, TwilioPricingRaw
from app.modules.sync_engine.hashing import payload_hash
from app.modules.twilio.geo_classify import (
    KEEP_COUNTRIES,
    classify_geo,
    keep_region_displays,
    locality_norm,
    region_norm,
)
from app.providers.twilio import contract
from app.providers.twilio.parser import CatalogRow, catalog_key, coverage_owner, parse_available_number

logger = logging.getLogger(__name__)

FIELD_VERIFICATION = {
    "country": "verified",
    "country_code": "verified",
    "beta": "verified",
    "subresource_uris": "verified",
    "current_price": "verified",
    "price_unit": "verified",
}

NUMBERS_STG_TABLE = "twilio_available_numbers_stg"


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
    iso, name, ntype = coverage_owner(
        country_iso=country_iso,
        country_name=country_name,
        number_type=number_type,
    )
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
        locality_raw = parsed["locality"]
        region_raw = parsed["region"]
        region, locality = classify_geo(
            country_iso=iso,
            country_name=name,
            region_raw=region_raw,
            locality_raw=locality_raw,
        )
        if locality_raw:
            cities.add((filter_key, locality_raw))
            had_geo = True
        if region_raw:
            regions.add(region_raw)
            had_geo = True
        elif filter_key:
            had_geo = True

        loc_norm = locality_norm(locality)
        reg_norm = region_norm(region)
        if locality or region or filter_key:
            geo_stmt = pg_insert(TwilioGeo).values(
                id=uuid.uuid4(),
                provider_id=provider_id,
                country_iso=iso,
                number_type=ntype,
                region_filter=filter_key,
                region=region,
                region_norm=reg_norm,
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
            country_iso=iso,
            country_name=name,
            number_type=ntype,
            region=region,
            locality=locality,
            region_raw=region_raw,
            locality_raw=locality_raw,
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
                "region_raw": number_stmt.excluded.region_raw,
                "locality_raw": number_stmt.excluded.locality_raw,
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
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
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


def drop_numbers_staging(db: Session) -> None:
    db.execute(text(f"DROP TABLE IF EXISTS {NUMBERS_STG_TABLE}"))
    db.commit()


def attach_numbers_progress_counts(
    progress: dict[str, Any],
    *,
    running: bool,
    counts: dict[tuple[str, str], int],
) -> dict[str, Any]:
    out = dict(progress)
    rows = [dict(row) for row in (out.get("rows") or [])]
    target = out.get("target") or {}
    iso = str(target.get("country_iso") or "").strip().upper()
    ntype = str(target.get("number_type") or "").strip()
    summary = dict(out.get("summary") or {})
    if running:
        this_run = int(rows[0].get("number_count") or 0) if rows else 0
        others = sum(
            int(cnt) for (country, typ), cnt in counts.items() if country != iso or typ != ntype
        )
        summary["numbers_unique"] = others + this_run
        out["summary"] = summary
        if rows:
            out["rows"] = rows
        return out
    if rows:
        fill_number_counts(rows, counts)
        out["rows"] = rows
    summary["numbers_unique"] = sum(int(cnt) for cnt in counts.values())
    out["summary"] = summary
    return out


def refresh_local_counts(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> tuple[int, int]:
    iso = country_iso.strip().upper()
    ntype = number_type.strip()
    region_count = (
        db.scalar(
            select(func.count(func.distinct(TwilioAvailableNumber.region))).where(
                TwilioAvailableNumber.provider_id == provider_id,
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
                TwilioAvailableNumber.region.is_not(None),
                TwilioAvailableNumber.region != "",
            )
        )
        or 0
    )
    city_count = (
        db.scalar(
            select(func.count(func.distinct(TwilioAvailableNumber.locality))).where(
                TwilioAvailableNumber.provider_id == provider_id,
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
                TwilioAvailableNumber.locality.is_not(None),
                TwilioAvailableNumber.locality != "",
            )
        )
        or 0
    )
    row = db.scalar(
        select(TwilioCatalog).where(
            TwilioCatalog.provider_id == provider_id,
            TwilioCatalog.country_iso == iso,
            TwilioCatalog.number_type == ntype,
        )
    )
    if row is not None:
        row.region_count = int(region_count)
        row.city_count = int(city_count)
    return int(region_count), int(city_count)


def finalize_coverage_geo(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
    job_id: uuid.UUID | None = None,
) -> tuple[int, int]:
    iso = country_iso.strip().upper()
    ntype = number_type.strip()
    rows = list(
        db.scalars(
            select(TwilioAvailableNumber).where(
                TwilioAvailableNumber.provider_id == provider_id,
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
            )
        ).all()
    )
    loaded = datetime.now(timezone.utc)
    country_name = rows[0].country_name if rows else None
    pairs: set[tuple[str | None, str | None]] = set()
    latest_job = job_id
    for row in rows:
        if row.region_raw is None and row.locality_raw is None:
            row.region_raw = row.region
            row.locality_raw = row.locality
        region, locality = classify_geo(
            country_iso=iso,
            country_name=row.country_name or country_name,
            region_raw=row.region_raw,
            locality_raw=row.locality_raw,
        )
        row.region = region
        row.locality = locality
        if region or locality:
            pairs.add((region, locality))
        if latest_job is None:
            latest_job = row.last_sync_job_id
    db.execute(
        delete(TwilioGeo).where(
            TwilioGeo.provider_id == provider_id,
            TwilioGeo.country_iso == iso,
            TwilioGeo.number_type == ntype,
            TwilioGeo.region_filter == "",
        )
    )
    for region, locality in pairs:
        db.execute(
            pg_insert(TwilioGeo)
            .values(
                id=uuid.uuid4(),
                provider_id=provider_id,
                country_iso=iso,
                number_type=ntype,
                region_filter="",
                region=region,
                region_norm=region_norm(region),
                locality=locality,
                locality_norm=locality_norm(locality),
                last_sync_job_id=latest_job,
            )
            .on_conflict_do_update(
                constraint="uq_twilio_geo_cell",
                set_={
                    "region": region,
                    "locality": locality,
                    "last_sync_job_id": latest_job,
                    "updated_at": loaded,
                },
            )
        )
    if iso in contract.NANP_COUNTRIES:
        for geo in db.scalars(
            select(TwilioGeo).where(
                TwilioGeo.provider_id == provider_id,
                TwilioGeo.country_iso == iso,
                TwilioGeo.number_type == ntype,
                TwilioGeo.region_filter != "",
            )
        ).all():
            display, _city = classify_geo(
                country_iso=iso,
                country_name=country_name,
                region_raw=geo.region_filter,
                locality_raw=None,
            )
            if display:
                geo.region = display
                geo.region_norm = region_norm(display)
    db.flush()
    return refresh_local_counts(
        db, provider_id=provider_id, country_iso=iso, number_type=ntype
    )


def finalize_all_geo(db: Session, *, provider_id: uuid.UUID) -> int:
    pairs = [
        ((row.country_iso or "").strip().upper(), (row.number_type or "").strip())
        for row in list_catalog_rows(db, provider_id=provider_id)
        if (row.country_iso or "").strip() and (row.number_type or "").strip()
    ]
    seen: set[tuple[str, str]] = set()
    updated = 0
    for iso, ntype in pairs:
        if (iso, ntype) in seen:
            continue
        seen.add((iso, ntype))
        finalize_coverage_geo(db, provider_id=provider_id, country_iso=iso, number_type=ntype)
        updated += 1
    extra = db.execute(
        select(
            TwilioAvailableNumber.country_iso,
            TwilioAvailableNumber.number_type,
        )
        .where(TwilioAvailableNumber.provider_id == provider_id)
        .distinct()
    ).all()
    for iso_raw, ntype_raw in extra:
        iso = str(iso_raw or "").strip().upper()
        ntype = str(ntype_raw or "").strip()
        if not iso or not ntype or (iso, ntype) in seen:
            continue
        finalize_coverage_geo(db, provider_id=provider_id, country_iso=iso, number_type=ntype)
        updated += 1
    return updated


def needs_geo_finalize(db: Session, *, provider_id: uuid.UUID) -> bool:
    rows = db.execute(
        select(
            TwilioAvailableNumber.country_iso,
            TwilioAvailableNumber.region,
        ).where(
            TwilioAvailableNumber.provider_id == provider_id,
            TwilioAvailableNumber.country_iso.in_(sorted(KEEP_COUNTRIES)),
            TwilioAvailableNumber.region.is_not(None),
            TwilioAvailableNumber.region != "",
        )
    ).all()
    allowed: dict[str, set[str]] = {}
    for iso, region in rows:
        country = str(iso or "").strip().upper()
        value = str(region or "").strip()
        if not country or not value:
            continue
        names = allowed.setdefault(country, {item.casefold() for item in keep_region_displays(country)})
        if value.casefold() not in names:
            return True
    return False


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
    return {
        (str(iso or "").strip().upper(), str(typ or "").strip()): int(cnt)
        for iso, typ, cnt in rows
    }


def realign_available_number_iso(db: Session, *, provider_id: uuid.UUID) -> dict[str, int]:
    """Move leaked E.164 back to the catalog pair that owns country_name + type."""
    result = db.execute(
        text(
            """
            UPDATE twilio_available_numbers AS n
            SET country_iso = c.country_iso,
                updated_at = NOW()
            FROM twilio_catalog AS c
            WHERE n.provider_id = :provider_id
              AND c.provider_id = n.provider_id
              AND c.is_currently_present IS TRUE
              AND n.country_name IS NOT NULL
              AND btrim(n.country_name) <> ''
              AND n.country_name = c.country_name
              AND n.number_type = c.number_type
              AND n.country_iso IS DISTINCT FROM c.country_iso
            """
        ),
        {"provider_id": provider_id},
    )
    db.flush()
    updated = int(result.rowcount or 0)
    if updated:
        logger.info(
            "Twilio realigned country_iso on %s available numbers provider_id=%s",
            updated,
            provider_id,
        )
    return {"realigned": updated}


def number_count_for_row(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> int:
    iso = (country_iso or "").strip().upper()
    ntype = (number_type or "").strip()
    return int(
        db.scalar(
            select(func.count())
            .select_from(TwilioAvailableNumber)
            .where(
                TwilioAvailableNumber.provider_id == provider_id,
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
            )
        )
        or 0
    )


def cutover_numbers_row(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> dict[str, int]:
    iso = (country_iso or "").strip().upper()
    ntype = (number_type or "").strip()
    previous = number_count_for_row(
        db, provider_id=provider_id, country_iso=iso, number_type=ntype
    )
    incoming = int(
        db.scalar(
            select(func.count())
            .select_from(TwilioAvailableNumber)
            .where(
                TwilioAvailableNumber.provider_id == provider_id,
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
                TwilioAvailableNumber.last_sync_job_id == job_id,
            )
        )
        or 0
    )
    if incoming <= 0 and previous > 0:
        raise EmptyTwilioFetchError(
            f"Twilio returned 0 numbers for {iso} {ntype}; refusing wipe (row has {previous})"
        )
    numbers_deleted = 0
    geo_deleted = 0
    if incoming > 0:
        numbers_deleted = int(
            db.execute(
                delete(TwilioAvailableNumber).where(
                    TwilioAvailableNumber.provider_id == provider_id,
                    TwilioAvailableNumber.country_iso == iso,
                    TwilioAvailableNumber.number_type == ntype,
                    TwilioAvailableNumber.last_sync_job_id.is_distinct_from(job_id),
                )
            ).rowcount
            or 0
        )
        geo_deleted = int(
            db.execute(
                delete(TwilioGeo).where(
                    TwilioGeo.provider_id == provider_id,
                    TwilioGeo.country_iso == iso,
                    TwilioGeo.number_type == ntype,
                    TwilioGeo.last_sync_job_id.is_distinct_from(job_id),
                )
            ).rowcount
            or 0
        )
        db.flush()
    return {
        "incoming": incoming,
        "previous": previous,
        "numbers_deleted": numbers_deleted,
        "geo_deleted": geo_deleted,
    }


def fill_number_counts(rows: list[dict[str, Any]], counts: dict[tuple[str, str], int]) -> None:
    for row in rows:
        iso = str(row.get("country_iso") or "").strip().upper()
        ntype = str(row.get("number_type") or "").strip()
        row["number_count"] = counts.get((iso, ntype), 0)


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
        payload["number_count"] = counts.get(
            ((row.country_iso or "").strip().upper(), (row.number_type or "").strip()),
            0,
        )
        out.append(payload)
    return out


def snapshot_totals(db: Session, *, provider_id: uuid.UUID) -> dict[str, int]:
    cities = (
        db.scalar(
            select(func.count()).select_from(
                select(
                    TwilioAvailableNumber.country_iso,
                    TwilioAvailableNumber.number_type,
                    TwilioAvailableNumber.locality,
                )
                .where(
                    TwilioAvailableNumber.provider_id == provider_id,
                    TwilioAvailableNumber.locality.is_not(None),
                    TwilioAvailableNumber.locality != "",
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


def list_catalog_rows(db: Session, *, provider_id: uuid.UUID) -> list[TwilioCatalog]:
    return list(
        db.scalars(
            select(TwilioCatalog)
            .where(
                TwilioCatalog.provider_id == provider_id,
                TwilioCatalog.is_currently_present.is_(True),
            )
            .order_by(TwilioCatalog.country_name.asc(), TwilioCatalog.number_type.asc())
        ).all()
    )


def load_row_known(
    db: Session,
    *,
    provider_id: uuid.UUID,
    country_iso: str,
    number_type: str,
) -> tuple[set[str], set[str], set[str]]:
    iso = country_iso.strip().upper()
    ntype = number_type.strip()
    phones = {
        str(phone)
        for phone in db.scalars(
            select(TwilioAvailableNumber.phone_number).where(
                TwilioAvailableNumber.provider_id == provider_id,
                TwilioAvailableNumber.country_iso == iso,
                TwilioAvailableNumber.number_type == ntype,
            )
        ).all()
        if str(phone or "").strip()
    }
    geo_rows = load_geo_rows(db, provider_id=provider_id, country_iso=iso, number_type=ntype)
    regions: set[str] = set()
    cities: set[str] = set()
    for row in geo_rows:
        region = (row.region or "").strip()
        if region:
            regions.add(region)
        region_filter = (row.region_filter or "").strip()
        if region_filter:
            regions.add(region_filter)
        locality = (row.locality or "").strip()
        if locality:
            cities.add(locality)
    return phones, regions, cities


def wipe_twilio_data(db: Session, *, provider_id: uuid.UUID) -> dict[str, int]:
    numbers = db.execute(
        delete(TwilioAvailableNumber).where(TwilioAvailableNumber.provider_id == provider_id)
    ).rowcount
    geo = db.execute(delete(TwilioGeo).where(TwilioGeo.provider_id == provider_id)).rowcount
    catalog = db.execute(
        delete(TwilioCatalog).where(TwilioCatalog.provider_id == provider_id)
    ).rowcount
    pricing = db.execute(delete(TwilioPricingRaw)).rowcount
    countries = db.execute(delete(TwilioCountryRaw)).rowcount
    db.commit()
    try:
        drop_numbers_staging(db)
    except Exception:
        logger.exception("Failed to drop Twilio numbers staging after wipe")
    return {
        "numbers": int(numbers or 0),
        "geo": int(geo or 0),
        "catalog": int(catalog or 0),
        "pricing": int(pricing or 0),
        "countries": int(countries or 0),
    }


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
