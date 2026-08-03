"""Persist phase: stage into TEMP tables, then atomic wipe+cutover."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models.catalog import NumberPriceHistory, NumbersCatalogNormalized, NumberStatusHistory
from app.models.enums import InventoryKind, ProviderCode
from app.models.runexis_raw import (
    RunexisCityRaw,
    RunexisFreeNumberRaw,
    RunexisPurchasedNumberRaw,
    RunexisRegionRaw,
)
from app.models.sipout_raw import (
    SipoutCityRaw,
    SipoutFreeNumberRaw,
    SipoutPurchasedNumberRaw,
    SipoutRegionRaw,
)
from app.modules.sync_engine.hashing import payload_hash
from app.modules.sync_engine.staging import (
    cutover_from_staging,
    ensure_temp_staging,
    insert_staging_batches,
)
from app.providers.dto.geo import ParsedCity, ParsedRegion
from app.providers.dto.numbers import NormalizedNumber


def _now() -> datetime:
    return datetime.now(timezone.utc)


def count_present_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    inventory_kind: InventoryKind,
) -> int:
    """How many currently present catalog rows exist for provider+kind."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(NumbersCatalogNormalized)
            .where(
                NumbersCatalogNormalized.provider_id == provider_id,
                NumbersCatalogNormalized.inventory_kind == inventory_kind,
                NumbersCatalogNormalized.is_currently_present.is_(True),
            )
        )
        or 0
    )


def wipe_provider_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    provider_code: ProviderCode,
    inventory_kind: InventoryKind,
) -> dict[str, int]:
    """Hard-delete catalog + history + raw for one provider inventory kind."""
    catalog_ids = select(NumbersCatalogNormalized.id).where(
        NumbersCatalogNormalized.provider_id == provider_id,
        NumbersCatalogNormalized.inventory_kind == inventory_kind,
    )
    price_del = db.execute(
        delete(NumberPriceHistory).where(NumberPriceHistory.catalog_id.in_(catalog_ids))
    )
    status_del = db.execute(
        delete(NumberStatusHistory).where(NumberStatusHistory.catalog_id.in_(catalog_ids))
    )
    catalog_del = db.execute(
        delete(NumbersCatalogNormalized).where(
            NumbersCatalogNormalized.provider_id == provider_id,
            NumbersCatalogNormalized.inventory_kind == inventory_kind,
        )
    )

    wiped_raw = 0
    if provider_code == ProviderCode.sipout:
        raw_cls = (
            SipoutFreeNumberRaw
            if inventory_kind == InventoryKind.free
            else SipoutPurchasedNumberRaw
        )
        wiped_raw = db.execute(delete(raw_cls)).rowcount or 0
    elif provider_code == ProviderCode.runexis:
        raw_cls = (
            RunexisFreeNumberRaw
            if inventory_kind == InventoryKind.free
            else RunexisPurchasedNumberRaw
        )
        wiped_raw = db.execute(delete(raw_cls)).rowcount or 0
    elif provider_code == ProviderCode.finenumbers:
        wiped_raw = 0
    else:
        raise ValueError(f"Unsupported provider for wipe: {provider_code}")

    db.flush()
    return {
        "wiped_catalog": catalog_del.rowcount or 0,
        "wiped_raw": wiped_raw,
        "wiped_price_history": price_del.rowcount or 0,
        "wiped_status_history": status_del.rowcount or 0,
    }


def _catalog_extra_fields(num: NormalizedNumber) -> dict[str, Any]:
    from app.modules.catalog.number_category import classify_number_category

    return {
        "abc_code": num.abc_code,
        "number_category": classify_number_category(num.abc_code, num.msisdn),
        "number_local": num.number_local,
        "mask": num.mask,
        "display_mask": num.display_mask,
        "book_date": num.book_date,
        "number_type": num.number_type,
        "points": num.points,
        "date_from": num.date_from,
        "operator_fas": num.operator_fas,
        "operator_id": num.operator_id,
        "last_operation_date": num.last_operation_date,
        "manager_id": num.manager_id,
        "notes": num.notes,
        "abcdef": num.abcdef,
        "order_id": num.order_id,
        "doc_status": num.doc_status,
        "doc_required": num.doc_required,
        "order_doc_required": num.order_doc_required,
        "sign": num.sign,
        "tariff": num.tariff,
        "number_class": num.number_class,
        "operator": num.operator,
        "partner": num.partner,
        "project": num.project,
        "equipment": num.equipment,
    }


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


def _catalog_row(
    num: NormalizedNumber,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    table_name: str,
    raw_id: uuid.UUID | None,
    loaded: datetime,
) -> dict[str, Any]:
    extra = _catalog_extra_fields(num)
    if "number_class" in extra:
        extra["class"] = extra.pop("number_class")
    conf = num.mapping_confidence
    conf_val = conf.value if hasattr(conf, "value") else conf
    return {
        "id": uuid.uuid4(),
        "provider_id": provider_id,
        "inventory_kind": inventory_kind.value,
        "provider_number_key": num.provider_number_key,
        "msisdn": num.msisdn,
        "region_external_id": num.region_external_id,
        "city_external_id": num.city_external_id,
        "region_name": num.region_name,
        "city_name": num.city_name,
        "buy_price": num.buy_price,
        "period_price": num.period_price,
        "status_raw": num.status_raw,
        "raw_source_table": table_name,
        "raw_source_id": raw_id,
        "last_sync_job_id": job_id,
        "field_verification": num.field_verification or {},
        "mapping_confidence": conf_val,
        "first_seen_at": loaded,
        "last_seen_at": loaded,
        "is_currently_present": True,
        "normalized_payload": num.normalized_payload or {},
        "created_at": loaded,
        "updated_at": loaded,
        **extra,
    }


def persist_sipout_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into TEMP tables, then atomic wipe+cutover (live untouched until cutover)."""
    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = (
        "sipout_free_numbers_raw"
        if inventory_kind == InventoryKind.free
        else "sipout_purchased_numbers_raw"
    )
    stg_raw_name = f"{table_name}_stg"
    stg_cat_name = "numbers_catalog_normalized_stg"

    stg_raw = ensure_temp_staging(db, live_table=table_name, stg_table=stg_raw_name)
    stg_cat = ensure_temp_staging(
        db, live_table="numbers_catalog_normalized", stg_table=stg_cat_name
    )

    raw_rows: list[dict[str, Any]] = []
    cat_rows: list[dict[str, Any]] = []
    for num in numbers:
        raw_id = uuid.uuid4()
        ph = payload_hash(num.raw_payload)
        if inventory_kind == InventoryKind.free:
            raw_rows.append(
                {
                    "id": raw_id,
                    "sync_job_id": job_id,
                    "source_loaded_at": loaded,
                    "raw_payload": num.raw_payload,
                    "payload_hash": ph,
                    "external_key": num.provider_number_key,
                    "did": num.provider_number_key,
                    "price": str(num.period_price) if num.period_price is not None else None,
                    "city_id": num.city_external_id,
                    "created_at": loaded,
                }
            )
        else:
            raw_rows.append(
                {
                    "id": raw_id,
                    "sync_job_id": job_id,
                    "source_loaded_at": loaded,
                    "raw_payload": num.raw_payload,
                    "payload_hash": ph,
                    "external_key": num.provider_number_key,
                    "did": num.provider_number_key,
                    "status": num.status_raw,
                    "city_id": num.city_external_id,
                    "has_sms": (
                        str(num.raw_payload.get("has_sms"))
                        if num.raw_payload.get("has_sms") is not None
                        else None
                    ),
                    "user_comment": (
                        str(num.raw_payload.get("user_comment"))
                        if num.raw_payload.get("user_comment") is not None
                        else None
                    ),
                    "order_id": (
                        str(num.raw_payload.get("order_id"))
                        if num.raw_payload.get("order_id") is not None
                        else None
                    ),
                    "doc_status": (
                        str(num.raw_payload.get("doc_status"))
                        if num.raw_payload.get("doc_status") is not None
                        else None
                    ),
                    "sign": (
                        str(num.raw_payload.get("sign"))
                        if num.raw_payload.get("sign") is not None
                        else None
                    ),
                    "created_at": loaded,
                }
            )
        cat_rows.append(
            _catalog_row(
                num,
                provider_id=provider_id,
                job_id=job_id,
                inventory_kind=inventory_kind,
                table_name=table_name,
                raw_id=raw_id,
                loaded=loaded,
            )
        )

    upserted = insert_staging_batches(
        db, stg_raw, raw_rows, on_progress=on_progress, progress_label="SipOut staging raw"
    )
    insert_staging_batches(
        db, stg_cat, cat_rows, on_progress=on_progress, progress_label="SipOut staging catalog"
    )

    wipe_holder: dict[str, int] = {}

    def _wipe() -> None:
        wipe_holder.update(
            wipe_provider_numbers(
                db,
                provider_id=provider_id,
                provider_code=ProviderCode.sipout,
                inventory_kind=inventory_kind,
            )
        )

    cutover_from_staging(
        db,
        wipe_fn=_wipe,
        live_raw_table=table_name,
        stg_raw=stg_raw,
        live_catalog_table="numbers_catalog_normalized",
        stg_catalog=stg_cat,
    )
    if on_progress:
        try:
            on_progress("cutover done", upserted, len(numbers))
        except Exception:
            logger.exception("persist on_progress failed")

    return {
        "upserted": upserted,
        "marked_absent": 0,
        "price_history": 0,
        "status_history": 0,
        "deduped_input": len(deduped),
        "bulk_insert": 1,
        "staged_cutover": 1,
        **wipe_holder,
    }


def persist_runexis_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into TEMP tables, then atomic wipe+cutover."""
    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = (
        "runexis_free_numbers_raw"
        if inventory_kind == InventoryKind.free
        else "runexis_purchased_numbers_raw"
    )
    default_source = (
        "numbering-api:search_numbers"
        if inventory_kind == InventoryKind.free
        else "api/v1/numbers/management"
    )
    stg_raw_name = f"{table_name}_stg"
    stg_cat_name = "numbers_catalog_normalized_stg"

    stg_raw = ensure_temp_staging(db, live_table=table_name, stg_table=stg_raw_name)
    stg_cat = ensure_temp_staging(
        db, live_table="numbers_catalog_normalized", stg_table=stg_cat_name
    )

    raw_rows: list[dict[str, Any]] = []
    cat_rows: list[dict[str, Any]] = []
    for num in numbers:
        raw_id = uuid.uuid4()
        ph = payload_hash(num.raw_payload)
        code = None
        for key in ("code", "city_code", "cityCode", "region_code"):
            if num.raw_payload.get(key) is not None:
                code = str(num.raw_payload.get(key))
                break
        local = None
        for key in ("number", "phone_number", "phoneNumber"):
            if num.raw_payload.get(key) is not None:
                local = str(num.raw_payload.get(key))
                break
        raw_rows.append(
            {
                "id": raw_id,
                "sync_job_id": job_id,
                "source_loaded_at": loaded,
                "raw_payload": num.raw_payload,
                "payload_hash": ph,
                "external_key": num.provider_number_key,
                "source_endpoint": default_source,
                "number_code": code,
                "number_local": local,
                "phone_number": num.msisdn,
                "city_external_id": num.city_external_id,
                "city_name": num.city_name,
                "region_name": num.region_name,
                "status_raw": num.status_raw,
                "price_installation": _decimal_or_none(
                    num.raw_payload.get("installationCost")
                    or num.raw_payload.get("installation_cost")
                ),
                "price_subscription": _decimal_or_none(
                    num.raw_payload.get("subscriptionFee")
                    or num.raw_payload.get("subscription_fee")
                ),
                "price_mera": _decimal_or_none(
                    num.raw_payload.get("meraPrice") or num.raw_payload.get("mera_price")
                ),
                "created_at": loaded,
            }
        )
        cat_rows.append(
            _catalog_row(
                num,
                provider_id=provider_id,
                job_id=job_id,
                inventory_kind=inventory_kind,
                table_name=table_name,
                raw_id=raw_id,
                loaded=loaded,
            )
        )

    upserted = insert_staging_batches(
        db, stg_raw, raw_rows, on_progress=on_progress, progress_label="Runexis staging raw"
    )
    insert_staging_batches(
        db, stg_cat, cat_rows, on_progress=on_progress, progress_label="Runexis staging catalog"
    )

    wipe_holder: dict[str, int] = {}

    def _wipe() -> None:
        wipe_holder.update(
            wipe_provider_numbers(
                db,
                provider_id=provider_id,
                provider_code=ProviderCode.runexis,
                inventory_kind=inventory_kind,
            )
        )

    cutover_from_staging(
        db,
        wipe_fn=_wipe,
        live_raw_table=table_name,
        stg_raw=stg_raw,
        live_catalog_table="numbers_catalog_normalized",
        stg_catalog=stg_cat,
    )
    if on_progress:
        try:
            on_progress("cutover done", upserted, len(numbers))
        except Exception:
            logger.exception("persist on_progress failed")

    return {
        "upserted": upserted,
        "marked_absent": 0,
        "price_history": 0,
        "status_history": 0,
        "deduped_input": len(deduped),
        "bulk_insert": 1,
        "staged_cutover": 1,
        **wipe_holder,
    }


def persist_finenumbers_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Catalog-only: stage then atomic wipe+cutover."""
    loaded = _now()
    table_name = "finenumbers_api"
    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num

    stg_cat = ensure_temp_staging(
        db, live_table="numbers_catalog_normalized", stg_table="numbers_catalog_normalized_stg"
    )
    cat_rows = [
        _catalog_row(
            num,
            provider_id=provider_id,
            job_id=job_id,
            inventory_kind=inventory_kind,
            table_name=table_name,
            raw_id=None,
            loaded=loaded,
        )
        for num in deduped.values()
    ]
    upserted = insert_staging_batches(
        db,
        stg_cat,
        cat_rows,
        on_progress=on_progress,
        progress_label="Finenumbers staging catalog",
    )

    wipe_holder: dict[str, int] = {}

    def _wipe() -> None:
        wipe_holder.update(
            wipe_provider_numbers(
                db,
                provider_id=provider_id,
                provider_code=ProviderCode.finenumbers,
                inventory_kind=inventory_kind,
            )
        )

    cutover_from_staging(
        db,
        wipe_fn=_wipe,
        live_raw_table=None,
        stg_raw=None,
        live_catalog_table="numbers_catalog_normalized",
        stg_catalog=stg_cat,
    )
    return {
        "upserted": upserted,
        "deduped_input": len(deduped),
        "staged_cutover": 1,
        **wipe_holder,
    }


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def build_city_lookup(db: Session, provider_code: str) -> dict[str, tuple[str | None, str | None, str | None]]:
    """city_id -> (city_name, region_external_id, region_name)."""
    lookup: dict[str, tuple[str | None, str | None, str | None]] = {}
    if provider_code == "finenumbers":
        return lookup
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
