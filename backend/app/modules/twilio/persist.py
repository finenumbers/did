"""Replace Twilio raw + catalog in one transaction. Empty incoming never wipes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.twilio import TwilioCatalog, TwilioCountryRaw, TwilioPricingRaw
from app.modules.sync_engine.hashing import payload_hash
from app.providers.twilio.parser import CatalogRow, catalog_key

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
    first_seen_by_key: dict[str, datetime] = dict(
        db.execute(
            select(TwilioCatalog.provider_group_key, TwilioCatalog.first_seen_at).where(
                TwilioCatalog.provider_id == provider_id
            )
        ).all()
    )
    db.execute(delete(TwilioCatalog).where(TwilioCatalog.provider_id == provider_id))
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
        db.add(
            TwilioCatalog(
                provider_id=provider_id,
                provider_group_key=key,
                country_name=row.country_name,
                country_iso=row.country_iso,
                number_type=row.number_type,
                period_price=row.period_price,
                price_unit=row.price_unit,
                country_beta=row.country_beta,
                field_verification=FIELD_VERIFICATION,
                last_sync_job_id=job_id,
                first_seen_at=first_seen_by_key.get(key, loaded),
                last_seen_at=loaded,
                is_currently_present=True,
            )
        )
        stored += 1

    db.flush()
    return {
        "countries": len(countries),
        "pricing": len(pricing_by_iso),
        "rows": stored,
    }
