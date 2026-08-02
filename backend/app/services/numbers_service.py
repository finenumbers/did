from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind, ProviderCode
from app.models.providers import Provider
from app.schemas.common import Page
from app.schemas.numbers import NumberItem


class NumbersService:
    SORTABLE = {
        "msisdn": NumbersCatalogNormalized.msisdn,
        "price_amount": NumbersCatalogNormalized.price_amount,
        "status_raw": NumbersCatalogNormalized.status_raw,
        "region_name": NumbersCatalogNormalized.region_name,
        "city_name": NumbersCatalogNormalized.city_name,
        "last_seen_at": NumbersCatalogNormalized.last_seen_at,
    }

    def __init__(self, db: Session):
        self.db = db

    def list_numbers(
        self,
        *,
        inventory_kind: InventoryKind,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
        provider: list[str] | None = None,
        region: str | None = None,
        city: str | None = None,
        status: str | None = None,
        has_sms: bool | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        q: str | None = None,
        is_currently_present: bool = True,
    ) -> Page[NumberItem]:
        stmt: Select = (
            select(NumbersCatalogNormalized, Provider.code)
            .join(Provider, Provider.id == NumbersCatalogNormalized.provider_id)
            .where(NumbersCatalogNormalized.inventory_kind == inventory_kind)
            .where(NumbersCatalogNormalized.is_currently_present.is_(is_currently_present))
        )
        if provider:
            codes = [ProviderCode(p) for p in provider]
            stmt = stmt.where(Provider.code.in_(codes))
        if region:
            stmt = stmt.where(
                (NumbersCatalogNormalized.region_name.ilike(f"%{region}%"))
                | (NumbersCatalogNormalized.region_external_id == region)
            )
        if city:
            stmt = stmt.where(
                (NumbersCatalogNormalized.city_name.ilike(f"%{city}%"))
                | (NumbersCatalogNormalized.city_external_id == city)
            )
        if status:
            stmt = stmt.where(NumbersCatalogNormalized.status_raw.ilike(f"%{status}%"))
        if has_sms is not None:
            stmt = stmt.where(NumbersCatalogNormalized.has_sms.is_(has_sms))
        if price_min is not None:
            stmt = stmt.where(NumbersCatalogNormalized.price_amount >= price_min)
        if price_max is not None:
            stmt = stmt.where(NumbersCatalogNormalized.price_amount <= price_max)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                (NumbersCatalogNormalized.msisdn.ilike(like))
                | (NumbersCatalogNormalized.provider_number_key.ilike(like))
            )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        col = self.SORTABLE.get(sort_by or "last_seen_at", NumbersCatalogNormalized.last_seen_at)
        stmt = stmt.order_by(col.desc() if sort_dir == "desc" else col.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = self.db.execute(stmt).all()
        items = [
            NumberItem(
                id=row.id,
                provider_code=code.value if hasattr(code, "value") else str(code),
                inventory_kind=row.inventory_kind.value,
                provider_number_key=row.provider_number_key,
                msisdn=row.msisdn,
                status_raw=row.status_raw,
                region_name=row.region_name,
                city_name=row.city_name,
                price_amount=row.price_amount,
                price_currency=row.price_currency,
                has_sms=row.has_sms,
                tariff_name=row.tariff_name,
                last_seen_at=row.last_seen_at,
                is_currently_present=row.is_currently_present,
                mapping_confidence=row.mapping_confidence.value,
                field_verification=row.field_verification or {},
            )
            for row, code in rows
        ]
        return Page.of(items, page=page, page_size=page_size, total=total)
