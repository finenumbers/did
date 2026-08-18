"""Persist phase: stage into UNLOGGED tables, then atomic wipe+cutover."""

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

from app.models.catalog import NumberPriceHistory, NumbersCatalogNormalized
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
from app.models.aurora_raw import AuroraFreeNumberRaw
from app.models.exolve_raw import (
    ExolveCategoryRaw,
    ExolveCityRaw,
    ExolveFreeNumberRaw,
    ExolveRegionRaw,
)
from app.models.uis_raw import UisFreeNumberRaw, UisPurchasedNumberRaw
from app.models.voximplant_raw import (
    VoximplantCategoryRaw,
    VoximplantCityRaw,
    VoximplantFreeNumberRaw,
    VoximplantRegionRaw,
)
from app.models.mcn_raw import McnCityRaw, McnFreeNumberRaw, McnRegionRaw
from app.providers.runexis import contract as runexis_contract
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
    """Hard-delete catalog + price history + raw for one provider inventory kind."""
    catalog_ids = select(NumbersCatalogNormalized.id).where(
        NumbersCatalogNormalized.provider_id == provider_id,
        NumbersCatalogNormalized.inventory_kind == inventory_kind,
    )
    db.execute(
        delete(NumberPriceHistory).where(NumberPriceHistory.catalog_id.in_(catalog_ids))
    )
    db.execute(
        delete(NumbersCatalogNormalized).where(
            NumbersCatalogNormalized.provider_id == provider_id,
            NumbersCatalogNormalized.inventory_kind == inventory_kind,
        )
    )

    if provider_code == ProviderCode.sipout:
        raw_cls = (
            SipoutFreeNumberRaw
            if inventory_kind == InventoryKind.free
            else SipoutPurchasedNumberRaw
        )
        db.execute(delete(raw_cls))
    elif provider_code == ProviderCode.runexis:
        raw_cls = (
            RunexisFreeNumberRaw
            if inventory_kind == InventoryKind.free
            else RunexisPurchasedNumberRaw
        )
        db.execute(delete(raw_cls))
    elif provider_code == ProviderCode.uis:
        raw_cls = (
            UisFreeNumberRaw
            if inventory_kind == InventoryKind.free
            else UisPurchasedNumberRaw
        )
        db.execute(delete(raw_cls))
    elif provider_code == ProviderCode.aurora:
        if inventory_kind != InventoryKind.free:
            raise ValueError("Aurora supports free inventory wipe only")
        db.execute(delete(AuroraFreeNumberRaw))
    elif provider_code == ProviderCode.exolve:
        if inventory_kind != InventoryKind.free:
            raise ValueError("Exolve supports free inventory wipe only")
        db.execute(delete(ExolveFreeNumberRaw))
    elif provider_code == ProviderCode.voximplant:
        if inventory_kind != InventoryKind.free:
            raise ValueError("Voximplant supports free inventory wipe only")
        db.execute(delete(VoximplantFreeNumberRaw))
    elif provider_code == ProviderCode.mcn:
        if inventory_kind != InventoryKind.free:
            raise ValueError("MCN supports free inventory wipe only")
        db.execute(delete(McnFreeNumberRaw))
    elif provider_code == ProviderCode.finenumbers:
        pass
    else:
        raise ValueError(f"Unsupported provider for wipe: {provider_code}")

    db.flush()
    return {}


def _catalog_extra_fields(num: NormalizedNumber) -> dict[str, Any]:
    from app.modules.catalog.number_category import classify_number_category

    return {
        "abc_code": num.abc_code,
        "number_category": classify_number_category(num.abc_code, num.msisdn),
        "number_local": num.number_local,
        "operator": num.operator,
        "rtu_connected": num.rtu_connected,
    }


def _region_model(provider_code: str):
    if provider_code == "sipout":
        return SipoutRegionRaw
    if provider_code == "runexis":
        return RunexisRegionRaw
    if provider_code == "exolve":
        return ExolveRegionRaw
    if provider_code == "voximplant":
        return VoximplantRegionRaw
    if provider_code == "mcn":
        return McnRegionRaw
    raise ValueError(f"Unsupported provider for regions: {provider_code}")


def _city_model(provider_code: str):
    if provider_code == "sipout":
        return SipoutCityRaw
    if provider_code == "runexis":
        return RunexisCityRaw
    if provider_code == "exolve":
        return ExolveCityRaw
    if provider_code == "voximplant":
        return VoximplantCityRaw
    if provider_code == "mcn":
        return McnCityRaw
    raise ValueError(f"Unsupported provider for cities: {provider_code}")


def _mcn_city_free_count(raw_payload: Any) -> int | None:
    if not isinstance(raw_payload, dict):
        return None
    try:
        if raw_payload.get("free_numbers_count") is None:
            return None
        return int(raw_payload.get("free_numbers_count"))
    except (TypeError, ValueError):
        return None


def persist_regions(
    db: Session,
    *,
    provider_code: str,
    job_id: uuid.UUID,
    regions: list[ParsedRegion],
) -> int:
    count = 0
    loaded = _now()
    model_cls = _region_model(provider_code)
    for region in regions:
        key = region.region_external_id
        ph = payload_hash(region.raw_payload)
        row = None
        if key:
            row = db.scalar(select(model_cls).where(model_cls.external_key == key))
        parent_id = None
        region_code = None
        category_name = None
        phone_count = None
        phone_price = None
        phone_installation_price = None
        if provider_code == "exolve" and isinstance(region.raw_payload, dict):
            parent_id = (
                str(region.raw_payload.get("parent_region_id"))
                if region.raw_payload.get("parent_region_id") is not None
                else None
            )
            region_code = (
                str(region.raw_payload.get("region_code")).strip()
                if region.raw_payload.get("region_code") is not None
                else None
            )
        if provider_code == "voximplant" and isinstance(region.raw_payload, dict):
            region_code = (
                str(region.raw_payload.get("region_code") or region.raw_payload.get("phone_region_code") or "").strip()
                or None
            )
            category_name = (
                str(region.raw_payload.get("phone_category_name") or "").strip() or None
            )
            try:
                phone_count = (
                    int(region.raw_payload.get("phone_count"))
                    if region.raw_payload.get("phone_count") is not None
                    else None
                )
            except (TypeError, ValueError):
                phone_count = None
            phone_price = region.raw_payload.get("phone_price")
            phone_installation_price = region.raw_payload.get("phone_installation_price")
        parent_id_mcn = None
        region_code_mcn = None
        if provider_code == "mcn" and isinstance(region.raw_payload, dict):
            parent_id_mcn = (
                str(region.raw_payload.get("parent_region_id"))
                if region.raw_payload.get("parent_region_id") is not None
                else None
            )
            region_code_mcn = (
                str(region.raw_payload.get("code") or region.raw_payload.get("key") or "").strip()
                or None
            )
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
            elif isinstance(row, ExolveRegionRaw):
                row.eng_name = region.eng_name
                row.parent_region_id = parent_id
                row.region_code = region_code
            elif isinstance(row, VoximplantRegionRaw):
                row.eng_name = region.eng_name
                row.region_code = region_code
                row.category_name = category_name
                row.phone_count = phone_count
                row.phone_price = phone_price
                row.phone_installation_price = phone_installation_price
            elif isinstance(row, McnRegionRaw):
                row.eng_name = region.eng_name
                row.parent_region_id = parent_id_mcn
                row.region_code = region_code_mcn
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
            elif provider_code == "exolve":
                kwargs.update(
                    eng_name=region.eng_name,
                    parent_region_id=parent_id,
                    region_code=region_code,
                )
            elif provider_code == "voximplant":
                kwargs.update(
                    eng_name=region.eng_name,
                    region_code=region_code,
                    category_name=category_name,
                    phone_count=phone_count,
                    phone_price=phone_price,
                    phone_installation_price=phone_installation_price,
                )
            elif provider_code == "mcn":
                kwargs.update(
                    eng_name=region.eng_name,
                    parent_region_id=parent_id_mcn,
                    region_code=region_code_mcn,
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
    model_cls = _city_model(provider_code)
    for city in cities:
        key = city.city_external_id
        ph = payload_hash(city.raw_payload)
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
                if isinstance(row, (ExolveCityRaw, VoximplantCityRaw, McnCityRaw)):
                    row.eng_name = city.eng_name
                if isinstance(row, McnCityRaw):
                    row.free_numbers_count = _mcn_city_free_count(city.raw_payload)
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
            elif provider_code == "exolve":
                db.add(
                    ExolveCityRaw(
                        sync_job_id=job_id,
                        source_loaded_at=loaded,
                        raw_payload=city.raw_payload,
                        payload_hash=ph,
                        external_key=key,
                        city_external_id=city.city_external_id,
                        city_name=city.name,
                        eng_name=city.eng_name,
                        region_external_id=city.region_external_id,
                        region_name=city.region_name,
                    )
                )
            elif provider_code == "voximplant":
                db.add(
                    VoximplantCityRaw(
                        sync_job_id=job_id,
                        source_loaded_at=loaded,
                        raw_payload=city.raw_payload,
                        payload_hash=ph,
                        external_key=key,
                        city_external_id=city.city_external_id,
                        city_name=city.name,
                        eng_name=city.eng_name,
                        region_external_id=city.region_external_id,
                        region_name=city.region_name,
                    )
                )
            elif provider_code == "mcn":
                db.add(
                    McnCityRaw(
                        sync_job_id=job_id,
                        source_loaded_at=loaded,
                        raw_payload=city.raw_payload,
                        payload_hash=ph,
                        external_key=key,
                        city_external_id=city.city_external_id,
                        city_name=city.name,
                        eng_name=city.eng_name,
                        region_external_id=city.region_external_id,
                        region_name=city.region_name,
                        free_numbers_count=_mcn_city_free_count(city.raw_payload),
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


def persist_exolve_categories(
    db: Session,
    *,
    job_id: uuid.UUID,
    categories: list[dict[str, Any]],
) -> int:
    """Replace-style upsert for Exolve GetList categories (by category_id)."""
    loaded = _now()
    count = 0
    for item in categories:
        key = item.get("category_external_id")
        if not key:
            continue
        raw = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else item
        ph = payload_hash(raw)
        row = db.scalar(
            select(ExolveCategoryRaw).where(ExolveCategoryRaw.external_key == str(key))
        )
        if row is None:
            db.add(
                ExolveCategoryRaw(
                    sync_job_id=job_id,
                    source_loaded_at=loaded,
                    raw_payload=raw,
                    payload_hash=ph,
                    external_key=str(key),
                    category_external_id=str(key),
                    category_name=item.get("category_name"),
                    type_id=item.get("type_id"),
                    type_name=item.get("type_name"),
                )
            )
        else:
            row.sync_job_id = job_id
            row.source_loaded_at = loaded
            row.raw_payload = raw
            row.payload_hash = ph
            row.category_external_id = str(key)
            row.category_name = item.get("category_name")
            row.type_id = item.get("type_id")
            row.type_name = item.get("type_name")
        count += 1
    db.flush()
    return count


def persist_voximplant_categories(
    db: Session,
    *,
    job_id: uuid.UUID,
    categories: list[dict[str, Any]],
) -> int:
    """Upsert Voximplant RU categories by phone_category_name."""
    loaded = _now()
    count = 0
    for item in categories:
        key = item.get("category_external_id")
        if not key:
            continue
        raw = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else item
        ph = payload_hash(raw)
        row = db.scalar(
            select(VoximplantCategoryRaw).where(
                VoximplantCategoryRaw.external_key == str(key)
            )
        )
        if row is None:
            db.add(
                VoximplantCategoryRaw(
                    sync_job_id=job_id,
                    source_loaded_at=loaded,
                    raw_payload=raw,
                    payload_hash=ph,
                    external_key=str(key),
                    category_external_id=str(key),
                    category_name=item.get("category_name"),
                    type_id=item.get("type_id"),
                    type_name=item.get("type_name"),
                )
            )
        else:
            row.sync_job_id = job_id
            row.source_loaded_at = loaded
            row.raw_payload = raw
            row.payload_hash = ph
            row.category_external_id = str(key)
            row.category_name = item.get("category_name")
            row.type_id = item.get("type_id")
            row.type_name = item.get("type_name")
        count += 1
    db.flush()
    return count


def load_present_operators(
    db: Session,
    *,
    provider_id: uuid.UUID,
    inventory_kind: InventoryKind,
) -> dict[str, str]:
    """msisdn → operator for currently present catalog rows (non-empty operator)."""
    rows = db.execute(
        select(NumbersCatalogNormalized.msisdn, NumbersCatalogNormalized.operator).where(
            NumbersCatalogNormalized.provider_id == provider_id,
            NumbersCatalogNormalized.inventory_kind == inventory_kind,
            NumbersCatalogNormalized.is_currently_present.is_(True),
            NumbersCatalogNormalized.msisdn.is_not(None),
            NumbersCatalogNormalized.operator.is_not(None),
            NumbersCatalogNormalized.operator != "",
        )
    ).all()
    out: dict[str, str] = {}
    for msisdn, operator in rows:
        if msisdn and operator and str(operator).strip():
            out[str(msisdn)] = str(operator).strip()
    return out


def preserve_operators_on_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
) -> int:
    """Copy previous catalog.operator onto incoming numbers when incoming has none.

    Interim buffer across wipe+cutover until Contour B PSTN enrich (last stage)
    overwrites or clears operator from cache/lookup.
    """
    prev = load_present_operators(
        db, provider_id=provider_id, inventory_kind=inventory_kind
    )
    if not prev:
        return 0
    preserved = 0
    for num in numbers:
        if num.operator and str(num.operator).strip():
            continue
        msisdn = num.msisdn or num.provider_number_key
        if not msisdn:
            continue
        op = prev.get(str(msisdn))
        if op:
            num.operator = op
            preserved += 1
    return preserved


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
    return {
        "id": uuid.uuid4(),
        "provider_id": provider_id,
        "inventory_kind": inventory_kind.value,
        "provider_number_key": num.provider_number_key,
        "msisdn": num.msisdn,
        "region_external_id": num.region_external_id,
        "city_external_id": num.city_external_id,
        # City/region stay empty here. PSTN fills mobile/800; geographic rows are
        # filled later from regions_directory (geographic_from_regions stage).
        "region_name": None,
        "city_name": None,
        "buy_price": num.buy_price,
        "period_price": num.period_price,
        "raw_source_table": table_name,
        "raw_source_id": raw_id,
        "last_sync_job_id": job_id,
        "field_verification": {},
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
    """Stage into UNLOGGED tables, then atomic wipe+cutover (live untouched until cutover)."""
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

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.sipout,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
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
    """Stage into UNLOGGED tables, then atomic wipe+cutover."""
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
        runexis_contract.NUMBERING_SOURCE_ENDPOINT
        if inventory_kind == InventoryKind.free
        else runexis_contract.GET_NUMBERS_MANAGEMENT
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

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.runexis,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
    }


def persist_uis_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into UNLOGGED tables, then atomic wipe+cutover."""
    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = (
        "uis_free_numbers_raw"
        if inventory_kind == InventoryKind.free
        else "uis_purchased_numbers_raw"
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
                    "phone": num.msisdn or num.provider_number_key,
                    "location_name": num.region_name,
                    "location_mnemonic": num.region_external_id,
                    "created_at": loaded,
                }
            )
        else:
            ext = num.raw_payload.get("id")
            raw_rows.append(
                {
                    "id": raw_id,
                    "sync_job_id": job_id,
                    "source_loaded_at": loaded,
                    "raw_payload": num.raw_payload,
                    "payload_hash": ph,
                    "external_key": num.provider_number_key,
                    "phone": num.msisdn,
                    "external_id": str(ext) if ext is not None else None,
                    "status": num.status_raw,
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
        db, stg_raw, raw_rows, on_progress=on_progress, progress_label="UIS staging raw"
    )
    insert_staging_batches(
        db, stg_cat, cat_rows, on_progress=on_progress, progress_label="UIS staging catalog"
    )

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.uis,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
    }


def persist_aurora_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into UNLOGGED tables, then atomic wipe+cutover (free only)."""
    if inventory_kind != InventoryKind.free:
        raise ValueError("Aurora persist supports free inventory only")

    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = "aurora_free_numbers_raw"
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
        raw_payload = num.raw_payload or {}
        raw_rows.append(
            {
                "id": raw_id,
                "sync_job_id": job_id,
                "source_loaded_at": loaded,
                "raw_payload": raw_payload,
                "payload_hash": ph,
                "external_key": num.provider_number_key,
                "phone": num.msisdn or num.provider_number_key,
                "period_price_raw": (
                    str(raw_payload.get("period_price_raw"))
                    if raw_payload.get("period_price_raw") is not None
                    else None
                ),
                "region_raw": (
                    str(raw_payload.get("region_raw"))
                    if raw_payload.get("region_raw") is not None
                    else None
                ),
                "city_name": num.city_name,
                "region_name": num.region_name,
                "display_mask": num.display_mask,
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
        db,
        stg_raw,
        raw_rows,
        on_progress=on_progress,
        progress_label="Aurora staging raw",
    )
    insert_staging_batches(
        db,
        stg_cat,
        cat_rows,
        on_progress=on_progress,
        progress_label="Aurora staging catalog",
    )

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.aurora,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
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

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.finenumbers,
            inventory_kind=inventory_kind,
        )

    cutover_from_staging(
        db,
        wipe_fn=_wipe,
        live_raw_table=None,
        stg_raw=None,
        live_catalog_table="numbers_catalog_normalized",
        stg_catalog=stg_cat,
    )
    if on_progress:
        try:
            on_progress("cutover done", upserted, len(deduped))
        except Exception:
            logger.exception("persist on_progress failed")
    return {
        "upserted": upserted,
        "deduped_input": len(deduped),
    }


def _purchased_match_key_row(row: NumbersCatalogNormalized) -> str | None:
    from app.providers.finenumbers.reg_mapper import catalog_match_key

    return catalog_match_key(row.abc_code, row.number_local, row.msisdn)


def snapshot_purchased_match_keys(
    db: Session,
    *,
    exclude_provider_id: uuid.UUID | None = None,
) -> set[str]:
    """Currently present purchased match keys (optionally excluding one provider)."""
    q = select(NumbersCatalogNormalized).where(
        NumbersCatalogNormalized.inventory_kind == InventoryKind.purchased,
        NumbersCatalogNormalized.is_currently_present.is_(True),
    )
    if exclude_provider_id is not None:
        q = q.where(NumbersCatalogNormalized.provider_id != exclude_provider_id)
    rows = db.scalars(q).all()
    keys: set[str] = set()
    for row in rows:
        k = _purchased_match_key_row(row)
        if k:
            keys.add(k)
    return keys


def apply_rtu_connected_flags(
    db: Session,
    *,
    reg_keys: set[str],
) -> dict[str, int]:
    """Set rtu_connected on all present purchased rows.

    Finenumbers + Frontier operator → Своя нумерация.
    Finenumbers + other/empty operator → Внешняя нумерация.
    Other provider + key in REG → Внешняя нумерация.
    Other provider + key not in REG → Не подключено.
    """
    from app.models.providers import Provider
    from app.providers.finenumbers import contract

    rows = db.execute(
        select(NumbersCatalogNormalized, Provider.code).join(
            Provider, Provider.id == NumbersCatalogNormalized.provider_id
        ).where(
            NumbersCatalogNormalized.inventory_kind == InventoryKind.purchased,
            NumbersCatalogNormalized.is_currently_present.is_(True),
        )
    ).all()
    own = 0
    external = 0
    not_connected = 0
    for row, provider_code in rows:
        code = provider_code.value if hasattr(provider_code, "value") else str(provider_code)
        if code == ProviderCode.finenumbers.value:
            if contract.is_frontier_operator(row.operator):
                row.rtu_connected = contract.RTU_OWN
                own += 1
            else:
                row.rtu_connected = contract.RTU_EXTERNAL
                external += 1
            continue
        key = _purchased_match_key_row(row)
        if key and key in reg_keys:
            row.rtu_connected = contract.RTU_EXTERNAL
            external += 1
        else:
            row.rtu_connected = contract.RTU_NOT_CONNECTED
            not_connected += 1
    db.flush()
    return {
        "rtu_own": own,
        "rtu_external": external,
        "rtu_not_connected": not_connected,
    }


def persist_finenumbers_reg_purchased(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, Any]:
    """Wipe+cutover finenumbers purchased for REG-only rows; then apply RTU flags.

    Duplicates already purchased by other providers are not inserted.
    Empty incoming is allowed (wipe REG-only slice when all REG numbers exist elsewhere).
    """
    from app.providers.finenumbers.reg_mapper import catalog_match_key, reg_key_set

    # Keys from earlier sync stages (not Finenumbers REG slice).
    early_keys = snapshot_purchased_match_keys(db, exclude_provider_id=provider_id)
    reg_keys = reg_key_set(numbers)
    only_reg: list[NormalizedNumber] = []
    for num in numbers:
        key = catalog_match_key(num.abc_code, num.number_local, num.msisdn)
        if key and key in early_keys:
            continue
        only_reg.append(num)

    persist_stats = persist_finenumbers_numbers(
        db,
        provider_id=provider_id,
        job_id=job_id,
        inventory_kind=InventoryKind.purchased,
        numbers=only_reg,
        on_progress=on_progress,
    )
    rtu_stats = apply_rtu_connected_flags(db, reg_keys=reg_keys)
    return {
        **persist_stats,
        **rtu_stats,
        "reg_total": len(reg_keys),
        "reg_inserted": len(only_reg),
        # Serializable for re-apply after operator enrichment.
        "reg_keys": sorted(reg_keys),
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
    if provider_code in {"finenumbers", "uis", "aurora"}:
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
    elif provider_code == "exolve":
        cities = db.scalars(select(ExolveCityRaw)).all()
        for c in cities:
            if not c.city_external_id:
                continue
            lookup[c.city_external_id] = (c.city_name, c.region_external_id, c.region_name)
    elif provider_code == "voximplant":
        cities = db.scalars(select(VoximplantCityRaw)).all()
        for c in cities:
            if not c.city_external_id:
                continue
            lookup[c.city_external_id] = (c.city_name, c.region_external_id, c.region_name)
    elif provider_code == "mcn":
        cities = db.scalars(select(McnCityRaw)).all()
        for c in cities:
            if not c.city_external_id:
                continue
            lookup[c.city_external_id] = (c.city_name, c.region_external_id, c.region_name)
    else:
        cities = db.scalars(select(RunexisCityRaw)).all()
        for c in cities:
            if not c.city_external_id:
                continue
            lookup[c.city_external_id] = (c.city_name, c.region_external_id, c.region_name)
    return lookup


def persist_exolve_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into UNLOGGED tables, then atomic wipe+cutover (free only)."""
    if inventory_kind != InventoryKind.free:
        raise ValueError("Exolve persist supports free inventory only")

    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = "exolve_free_numbers_raw"
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
        buy = num.buy_price
        period = num.period_price
        raw_rows.append(
            {
                "id": raw_id,
                "sync_job_id": job_id,
                "source_loaded_at": loaded,
                "raw_payload": num.raw_payload,
                "payload_hash": ph,
                "external_key": num.provider_number_key,
                "phone": num.msisdn or num.provider_number_key,
                "region_name": num.region_name or num.city_name,
                "install_fee": buy,
                "subscription_fee": period,
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
        db,
        stg_raw,
        raw_rows,
        on_progress=on_progress,
        progress_label="Exolve staging raw",
    )
    insert_staging_batches(
        db,
        stg_cat,
        cat_rows,
        on_progress=on_progress,
        progress_label="Exolve staging catalog",
    )

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.exolve,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
    }


def persist_voximplant_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into UNLOGGED tables, then atomic wipe+cutover (free only)."""
    if inventory_kind != InventoryKind.free:
        raise ValueError("Voximplant persist supports free inventory only")

    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = "voximplant_free_numbers_raw"
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
        buy = num.buy_price
        period = num.period_price
        raw_rows.append(
            {
                "id": raw_id,
                "sync_job_id": job_id,
                "source_loaded_at": loaded,
                "raw_payload": num.raw_payload,
                "payload_hash": ph,
                "external_key": num.provider_number_key,
                "phone": num.msisdn or num.provider_number_key,
                "region_name": num.region_name or num.city_name,
                "install_fee": buy,
                "subscription_fee": period,
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
        db,
        stg_raw,
        raw_rows,
        on_progress=on_progress,
        progress_label="Voximplant staging raw",
    )
    insert_staging_batches(
        db,
        stg_cat,
        cat_rows,
        on_progress=on_progress,
        progress_label="Voximplant staging catalog",
    )

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.voximplant,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
    }


def persist_mcn_numbers(
    db: Session,
    *,
    provider_id: uuid.UUID,
    job_id: uuid.UUID,
    inventory_kind: InventoryKind,
    numbers: list[NormalizedNumber],
    on_progress: Callable[[str, int | None, int | None], Any] | None = None,
) -> dict[str, int]:
    """Stage into UNLOGGED tables, then atomic wipe+cutover (free only)."""
    if inventory_kind != InventoryKind.free:
        raise ValueError("MCN persist supports free inventory only")

    deduped: dict[str, NormalizedNumber] = {}
    for num in numbers:
        if num.provider_number_key:
            deduped[num.provider_number_key] = num
    numbers = list(deduped.values())

    loaded = _now()
    table_name = "mcn_free_numbers_raw"
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
        buy = num.buy_price
        period = num.period_price
        raw_rows.append(
            {
                "id": raw_id,
                "sync_job_id": job_id,
                "source_loaded_at": loaded,
                "raw_payload": num.raw_payload,
                "payload_hash": ph,
                "external_key": num.provider_number_key,
                "phone": num.msisdn or num.provider_number_key,
                "region_name": num.region_name or num.city_name,
                "install_fee": buy,
                "subscription_fee": period,
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
        db,
        stg_raw,
        raw_rows,
        on_progress=on_progress,
        progress_label="MCN staging raw",
    )
    insert_staging_batches(
        db,
        stg_cat,
        cat_rows,
        on_progress=on_progress,
        progress_label="MCN staging catalog",
    )

    def _wipe() -> None:
        wipe_provider_numbers(
            db,
            provider_id=provider_id,
            provider_code=ProviderCode.mcn,
            inventory_kind=inventory_kind,
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
        "deduped_input": len(deduped),
    }
