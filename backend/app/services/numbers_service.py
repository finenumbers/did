from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Select, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement
from sqlalchemy.types import String

from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind, MappingConfidence, ProviderCode
from app.models.providers import Provider
from app.schemas.common import Page
from app.schemas.numbers import FacetItem, FacetResponse, NumberItem

EMPTY_TOKEN = "__empty__"


def _format_price_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        n = int(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    sign = "-" if n < 0 else ""
    digits = str(abs(n))
    parts: list[str] = []
    while digits:
        parts.append(digits[-3:])
        digits = digits[:-3]
    return sign + " ".join(reversed(parts))


def _format_points_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _parse_price_token(token: str) -> Decimal | None:
    raw = token.replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _parse_points_token(token: str) -> Decimal | None:
    raw = token.replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


class NumbersService:
    """List + facet queries over numbers_catalog_normalized."""

    TEXT_COLUMNS: dict[str, Any] = {
        "provider_number_key": NumbersCatalogNormalized.provider_number_key,
        "msisdn": NumbersCatalogNormalized.msisdn,
        "abc_code": NumbersCatalogNormalized.abc_code,
        "number_category": NumbersCatalogNormalized.number_category,
        "number_local": NumbersCatalogNormalized.number_local,
        "region_name": NumbersCatalogNormalized.region_name,
        "city_name": NumbersCatalogNormalized.city_name,
        "mask": NumbersCatalogNormalized.mask,
        "display_mask": NumbersCatalogNormalized.display_mask,
        "number_type": NumbersCatalogNormalized.number_type,
        "notes": NumbersCatalogNormalized.notes,
        "class": NumbersCatalogNormalized.number_class,
        "operator": NumbersCatalogNormalized.operator,
        "rtu_connected": NumbersCatalogNormalized.rtu_connected,
    }

    PRICE_COLUMNS = {
        "buy_price": NumbersCatalogNormalized.buy_price,
        "period_price": NumbersCatalogNormalized.period_price,
    }
    POINTS_COLUMN = "points"
    PROVIDER_CODE = "provider_code"
    MAPPING_CONFIDENCE = "mapping_confidence"

    FACET_COLUMNS = frozenset(
        {
            PROVIDER_CODE,
            "abc_code",
            "number_category",
            "number_local",
            "region_name",
            "city_name",
            "buy_price",
            "period_price",
            "mask",
            "display_mask",
            "number_type",
            POINTS_COLUMN,
            "notes",
            "class",
            "operator",
            "rtu_connected",
            MAPPING_CONFIDENCE,
        }
    )

    SORTABLE = {
        "msisdn": NumbersCatalogNormalized.msisdn,
        "number_local": NumbersCatalogNormalized.number_local,
        "abc_code": NumbersCatalogNormalized.abc_code,
        "number_category": NumbersCatalogNormalized.number_category,
        "provider_number_key": NumbersCatalogNormalized.provider_number_key,
        "buy_price": NumbersCatalogNormalized.buy_price,
        "period_price": NumbersCatalogNormalized.period_price,
        "points": NumbersCatalogNormalized.points,
        "region_name": NumbersCatalogNormalized.region_name,
        "city_name": NumbersCatalogNormalized.city_name,
        "mask": NumbersCatalogNormalized.mask,
        "number_type": NumbersCatalogNormalized.number_type,
        "class": NumbersCatalogNormalized.number_class,
        "operator": NumbersCatalogNormalized.operator,
        "rtu_connected": NumbersCatalogNormalized.rtu_connected,
        "mapping_confidence": NumbersCatalogNormalized.mapping_confidence,
    }

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def parse_filters(filters: str | dict[str, list[str]] | None) -> dict[str, list[str]]:
        if filters is None or filters == "":
            return {}
        if isinstance(filters, dict):
            data = filters
        else:
            try:
                data = json.loads(filters)
            except json.JSONDecodeError as exc:
                raise ValueError("filters must be a JSON object") from exc
        if not isinstance(data, dict):
            raise ValueError("filters must be a JSON object")
        out: dict[str, list[str]] = {}
        for key, values in data.items():
            if not isinstance(key, str):
                continue
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            cleaned = [str(v) for v in values if v is not None]
            if cleaned:
                out[key] = cleaned
        return out

    def _base_stmt(self, inventory_kind: InventoryKind, *, is_currently_present: bool = True) -> Select:
        return (
            select(NumbersCatalogNormalized, Provider.code)
            .join(Provider, Provider.id == NumbersCatalogNormalized.provider_id)
            .where(NumbersCatalogNormalized.inventory_kind == inventory_kind)
            .where(NumbersCatalogNormalized.is_currently_present.is_(is_currently_present))
        )

    def _apply_text_q(
        self,
        stmt: Select,
        *,
        number_local_q: str | None,
        msisdn_q: str | None,
        provider_number_key_q: str | None,
        q: str | None,
    ) -> Select:
        if number_local_q:
            stmt = stmt.where(
                NumbersCatalogNormalized.number_local.ilike(f"%{number_local_q}%")
            )
        if msisdn_q:
            stmt = stmt.where(NumbersCatalogNormalized.msisdn.ilike(f"%{msisdn_q}%"))
        if provider_number_key_q:
            stmt = stmt.where(
                NumbersCatalogNormalized.provider_number_key.ilike(f"%{provider_number_key_q}%")
            )
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                (NumbersCatalogNormalized.number_local.ilike(like))
                | (NumbersCatalogNormalized.msisdn.ilike(like))
                | (NumbersCatalogNormalized.provider_number_key.ilike(like))
            )
        return stmt

    def _empty_predicate(self, col: ColumnElement[Any]) -> ColumnElement[Any]:
        return or_(col.is_(None), cast(col, String) == "")

    def _apply_facet_filters(
        self,
        stmt: Select,
        filters: dict[str, list[str]],
        *,
        exclude_column: str | None = None,
    ) -> Select:
        for field, values in filters.items():
            if field == exclude_column:
                continue
            if field not in self.FACET_COLUMNS:
                continue
            if not values:
                continue

            include_empty = EMPTY_TOKEN in values or "" in values
            concrete = [v for v in values if v not in (EMPTY_TOKEN, "")]

            if field == self.PROVIDER_CODE:
                codes: list[ProviderCode] = []
                for v in concrete:
                    try:
                        codes.append(ProviderCode(v))
                    except ValueError:
                        continue
                preds = []
                if codes:
                    preds.append(Provider.code.in_(codes))
                if include_empty:
                    preds.append(Provider.code.is_(None))
                if preds:
                    stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
                continue

            if field == self.MAPPING_CONFIDENCE:
                enums: list[MappingConfidence] = []
                for v in concrete:
                    try:
                        enums.append(MappingConfidence(v))
                    except ValueError:
                        continue
                preds = []
                if enums:
                    preds.append(NumbersCatalogNormalized.mapping_confidence.in_(enums))
                if include_empty:
                    preds.append(NumbersCatalogNormalized.mapping_confidence.is_(None))
                if preds:
                    stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
                continue

            if field in self.PRICE_COLUMNS:
                col = self.PRICE_COLUMNS[field]
                preds = []
                nums = [n for n in (_parse_price_token(v) for v in concrete) if n is not None]
                if nums:
                    preds.append(func.round(col).in_([int(n) for n in nums]))
                if include_empty:
                    preds.append(col.is_(None))
                if preds:
                    stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
                continue

            if field == self.POINTS_COLUMN:
                col = NumbersCatalogNormalized.points
                preds = []
                nums = [n for n in (_parse_points_token(v) for v in concrete) if n is not None]
                if nums:
                    preds.append(func.round(col, 2).in_(nums))
                if include_empty:
                    preds.append(col.is_(None))
                if preds:
                    stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
                continue

            col = self.TEXT_COLUMNS.get(field)
            if col is None:
                continue
            preds = []
            if concrete:
                preds.append(col.in_(concrete))
            if include_empty:
                preds.append(self._empty_predicate(col))
            if preds:
                stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
        return stmt

    def apply_catalog_filters(
        self,
        stmt: Select,
        *,
        filters: dict[str, list[str]] | None = None,
        number_local_q: str | None = None,
        msisdn_q: str | None = None,
        provider_number_key_q: str | None = None,
        q: str | None = None,
        exclude_column: str | None = None,
        provider: list[str] | None = None,
        region: str | None = None,
        city: str | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
    ) -> Select:
        merged = dict(filters or {})
        if provider:
            merged.setdefault(self.PROVIDER_CODE, list(provider))
        stmt = self._apply_facet_filters(stmt, merged, exclude_column=exclude_column)
        stmt = self._apply_text_q(
            stmt,
            number_local_q=number_local_q,
            msisdn_q=msisdn_q,
            provider_number_key_q=provider_number_key_q,
            q=q,
        )
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
        if price_min is not None:
            stmt = stmt.where(
                or_(
                    NumbersCatalogNormalized.buy_price >= price_min,
                    NumbersCatalogNormalized.period_price >= price_min,
                )
            )
        if price_max is not None:
            stmt = stmt.where(
                or_(
                    NumbersCatalogNormalized.buy_price <= price_max,
                    NumbersCatalogNormalized.period_price <= price_max,
                )
            )
        return stmt

    def _row_to_item(self, row: NumbersCatalogNormalized, code: Any) -> NumberItem:
        return NumberItem(
            id=row.id,
            provider_code=code.value if hasattr(code, "value") else str(code),
            inventory_kind=row.inventory_kind.value,
            provider_number_key=row.provider_number_key,
            msisdn=row.msisdn,
            abc_code=row.abc_code,
            number_category=row.number_category,
            number_local=row.number_local,
            region_name=row.region_name,
            city_name=row.city_name,
            buy_price=row.buy_price,
            period_price=row.period_price,
            mask=row.mask,
            display_mask=row.display_mask,
            number_type=row.number_type,
            points=row.points,
            notes=row.notes,
            number_class=row.number_class,
            operator=row.operator,
            rtu_connected=row.rtu_connected,
            is_currently_present=row.is_currently_present,
            mapping_confidence=row.mapping_confidence.value,
        )

    def order_by_clauses(self, sort_by: str | None, sort_dir: str) -> list[Any]:
        """Default: ABC, then number_local. Always stable by id."""
        primary = self.SORTABLE.get(
            sort_by or "abc_code", NumbersCatalogNormalized.abc_code
        )
        directed = primary.desc() if sort_dir == "desc" else primary.asc()
        clauses: list[Any] = [directed]
        if primary is not NumbersCatalogNormalized.abc_code:
            clauses.append(
                NumbersCatalogNormalized.abc_code.desc()
                if sort_dir == "desc"
                else NumbersCatalogNormalized.abc_code.asc()
            )
        if primary is not NumbersCatalogNormalized.number_local:
            clauses.append(
                NumbersCatalogNormalized.number_local.desc()
                if sort_dir == "desc"
                else NumbersCatalogNormalized.number_local.asc()
            )
        clauses.append(NumbersCatalogNormalized.id.asc())
        return clauses

    def list_numbers(
        self,
        *,
        inventory_kind: InventoryKind,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]] | None = None,
        number_local_q: str | None = None,
        msisdn_q: str | None = None,
        provider_number_key_q: str | None = None,
        provider: list[str] | None = None,
        region: str | None = None,
        city: str | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        q: str | None = None,
        is_currently_present: bool = True,
    ) -> Page[NumberItem]:
        stmt = self._base_stmt(inventory_kind, is_currently_present=is_currently_present)
        stmt = self.apply_catalog_filters(
            stmt,
            filters=filters,
            number_local_q=number_local_q,
            msisdn_q=msisdn_q,
            provider_number_key_q=provider_number_key_q,
            q=q,
            provider=provider,
            region=region,
            city=city,
            price_min=price_min,
            price_max=price_max,
        )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = stmt.order_by(*self.order_by_clauses(sort_by, sort_dir))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = self.db.execute(stmt).all()
        items = [self._row_to_item(row, code) for row, code in rows]
        return Page.of(items, page=page, page_size=page_size, total=total)

    def _facet_value_expr(self, column: str) -> ColumnElement[Any]:
        if column == self.PROVIDER_CODE:
            return cast(Provider.code, String)
        if column == self.MAPPING_CONFIDENCE:
            return cast(NumbersCatalogNormalized.mapping_confidence, String)
        if column in self.PRICE_COLUMNS:
            return func.round(self.PRICE_COLUMNS[column])
        if column == self.POINTS_COLUMN:
            return func.round(NumbersCatalogNormalized.points, 2)
        col = self.TEXT_COLUMNS.get(column)
        if col is None:
            raise ValueError(f"Unsupported facet column: {column}")
        return col

    def _format_facet_value(self, column: str, raw: Any) -> str:
        if raw is None:
            return ""
        if column in self.PRICE_COLUMNS:
            return _format_price_value(raw)
        if column == self.POINTS_COLUMN:
            return _format_points_value(raw)
        if column in (self.PROVIDER_CODE, self.MAPPING_CONFIDENCE):
            return raw.value if hasattr(raw, "value") else str(raw)
        return str(raw)

    def list_facets(
        self,
        *,
        inventory_kind: InventoryKind,
        column: str,
        filters: dict[str, list[str]] | None = None,
        number_local_q: str | None = None,
        msisdn_q: str | None = None,
        provider_number_key_q: str | None = None,
        q: str | None = None,
        limit: int = 200,
        offset: int = 0,
        is_currently_present: bool = True,
    ) -> FacetResponse:
        if column not in self.FACET_COLUMNS:
            raise ValueError(f"Unsupported facet column: {column}")

        value_expr = self._facet_value_expr(column)
        if column in self.TEXT_COLUMNS:
            value_expr = func.nullif(func.btrim(cast(value_expr, String)), "")

        stmt = self._base_stmt(inventory_kind, is_currently_present=is_currently_present)
        stmt = self.apply_catalog_filters(
            stmt,
            filters=filters,
            number_local_q=number_local_q,
            msisdn_q=msisdn_q,
            provider_number_key_q=provider_number_key_q,
            exclude_column=column,
        )

        base = (
            stmt.with_only_columns(
                value_expr.label("facet_value"),
                NumbersCatalogNormalized.id.label("row_id"),
            )
            .order_by(None)
            .subquery()
        )

        grouped = select(
            base.c.facet_value,
            func.count().label("cnt"),
        ).group_by(base.c.facet_value)

        if q:
            like = f"%{q}%"
            grouped = grouped.where(cast(base.c.facet_value, String).ilike(like))

        grouped = grouped.order_by(
            func.count().desc(),
            cast(base.c.facet_value, String).asc().nulls_last(),
        )

        rows = self.db.execute(grouped.offset(offset).limit(limit + 1)).all()
        truncated = len(rows) > limit
        rows = rows[:limit]

        items = [
            FacetItem(value=self._format_facet_value(column, raw), count=int(cnt))
            for raw, cnt in rows
        ]
        return FacetResponse(column=column, items=items, truncated=truncated)
