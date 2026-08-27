from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Select, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement
from sqlalchemy.types import String

from app.models.twilio import TwilioAvailableNumber, TwilioCatalog
from app.schemas.common import Page
from app.schemas.twilio import (
    TwilioCoverageItem,
    TwilioFacetItem,
    TwilioFacetResponse,
    TwilioNumberItem,
)
from app.services.didww_service import format_didww_price
from app.services.numbers_service import EMPTY_TOKEN, _parse_price_token
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook

BOOL_TRUE = "да"
BOOL_FALSE = "нет"

TWILIO_XLSX_SHEET = "twilio"
TWILIO_XLSX_HEADERS = ["Страна", "ISO", "Тип", "Абонплата", "Валюта", "Beta"]


def format_twilio_price(value: Any) -> str:
    return format_didww_price(value)


class TwilioCatalogService:
    TEXT_COLUMNS: dict[str, Any] = {
        "country_name": TwilioCatalog.country_name,
        "country_iso": TwilioCatalog.country_iso,
        "number_type": TwilioCatalog.number_type,
        "price_unit": TwilioCatalog.price_unit,
    }
    PRICE_COLUMNS = {
        "period_price": TwilioCatalog.period_price,
    }
    BOOL_COLUMNS = {
        "country_beta": TwilioCatalog.country_beta,
    }
    FACET_COLUMNS = frozenset(set(TEXT_COLUMNS) | set(PRICE_COLUMNS) | set(BOOL_COLUMNS))
    SORTABLE = {
        "country_name": TwilioCatalog.country_name,
        "country_iso": TwilioCatalog.country_iso,
        "number_type": TwilioCatalog.number_type,
        "period_price": TwilioCatalog.period_price,
        "price_unit": TwilioCatalog.price_unit,
        "country_beta": TwilioCatalog.country_beta,
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

    def _base(self) -> Select:
        return select(TwilioCatalog).where(TwilioCatalog.is_currently_present.is_(True))

    def _empty_pred(self, col: ColumnElement[Any]) -> ColumnElement[Any]:
        return or_(col.is_(None), cast(col, String) == "")

    def _apply_filters(
        self,
        stmt: Select,
        filters: dict[str, list[str]],
        *,
        q: str | None = None,
        exclude_column: str | None = None,
    ) -> Select:
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    TwilioCatalog.country_name.ilike(like),
                    TwilioCatalog.country_iso.ilike(like),
                    TwilioCatalog.number_type.ilike(like),
                    TwilioCatalog.price_unit.ilike(like),
                )
            )
        for field, values in filters.items():
            if field == exclude_column or field not in self.FACET_COLUMNS or not values:
                continue
            include_empty = EMPTY_TOKEN in values or "" in values
            concrete = [v for v in values if v not in (EMPTY_TOKEN, "")]
            preds: list[Any] = []
            if field in self.PRICE_COLUMNS:
                col = self.PRICE_COLUMNS[field]
                nums = [n for n in (_parse_price_token(v) for v in concrete) if n is not None]
                if nums:
                    preds.append(col.in_(nums))
                if include_empty:
                    preds.append(col.is_(None))
            elif field in self.BOOL_COLUMNS:
                col = self.BOOL_COLUMNS[field]
                wanted: list[bool] = []
                for v in concrete:
                    if v == BOOL_TRUE:
                        wanted.append(True)
                    elif v == BOOL_FALSE:
                        wanted.append(False)
                if wanted:
                    preds.append(col.in_(wanted))
                if include_empty:
                    preds.append(col.is_(None))
            else:
                col = self.TEXT_COLUMNS[field]
                if concrete:
                    preds.append(col.in_(concrete))
                if include_empty:
                    preds.append(self._empty_pred(col))
            if preds:
                stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
        return stmt

    def list_coverage(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ) -> Page[TwilioCoverageItem]:
        stmt = self._apply_filters(self._base(), filters, q=q)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        col = self.SORTABLE.get(sort_by or "", TwilioCatalog.country_name)
        order = col.asc() if sort_dir != "desc" else col.desc()
        rows = self.db.scalars(
            stmt.order_by(order, TwilioCatalog.number_type.asc(), TwilioCatalog.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        from app.modules.twilio.persist import catalog_numbers_loaded, number_counts_by_type

        provider_id = rows[0].provider_id if rows else self.db.scalar(
            select(TwilioCatalog.provider_id).limit(1)
        )
        counts = number_counts_by_type(self.db, provider_id=provider_id) if provider_id else {}
        items = []
        for row in rows:
            loaded = catalog_numbers_loaded(row)
            items.append(
                TwilioCoverageItem(
                    id=row.id,
                    provider_group_key=row.provider_group_key,
                    country_name=row.country_name,
                    country_iso=row.country_iso,
                    number_type=row.number_type,
                    period_price=row.period_price,
                    price_unit=row.price_unit,
                    country_beta=row.country_beta,
                    region_count=row.region_count,
                    city_count=row.city_count,
                    number_count=counts.get(
                        ((row.country_iso or "").strip().upper(), (row.number_type or "").strip()),
                        0,
                    ),
                    numbers_synced_at=row.numbers_synced_at,
                    numbers_loaded=loaded,
                )
            )
        return Page.of(items, page=page, page_size=page_size, total=int(total))

    def iter_coverage(
        self,
        *,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ):
        stmt = self._apply_filters(self._base(), filters, q=q)
        col = self.SORTABLE.get(sort_by or "", TwilioCatalog.country_name)
        order = col.asc() if sort_dir != "desc" else col.desc()
        yield from self.db.scalars(
            stmt.order_by(order, TwilioCatalog.number_type.asc(), TwilioCatalog.id.asc())
        )

    def _facet_value_expr(self, column: str) -> ColumnElement[Any]:
        if column in self.PRICE_COLUMNS:
            return self.PRICE_COLUMNS[column]
        if column in self.BOOL_COLUMNS:
            col = self.BOOL_COLUMNS[column]
            return case((col.is_(True), BOOL_TRUE), (col.is_(False), BOOL_FALSE), else_=None)
        return func.nullif(func.btrim(cast(self.TEXT_COLUMNS[column], String)), "")

    def list_facets(
        self,
        *,
        column: str,
        filters: dict[str, list[str]],
        q: str | None,
        value_q: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> TwilioFacetResponse:
        if column not in self.FACET_COLUMNS:
            raise ValueError(f"Unknown facet column: {column}")
        stmt = self._apply_filters(self._base(), filters, q=q, exclude_column=column)
        base = (
            stmt.with_only_columns(
                self._facet_value_expr(column).label("facet_value"),
                TwilioCatalog.id.label("row_id"),
            )
            .order_by(None)
            .subquery()
        )
        grouped = select(base.c.facet_value, func.count().label("cnt")).group_by(
            base.c.facet_value
        )
        if value_q:
            grouped = grouped.where(cast(base.c.facet_value, String).ilike(f"%{value_q}%"))
        numeric_facet = column in self.PRICE_COLUMNS
        tie_break = base.c.facet_value if numeric_facet else cast(base.c.facet_value, String)
        grouped = grouped.order_by(func.count().desc(), tie_break.asc().nulls_last())
        rows = self.db.execute(grouped.offset(offset).limit(limit + 1)).all()
        truncated = len(rows) > limit
        items = []
        for value, cnt in rows[:limit]:
            if column in self.PRICE_COLUMNS:
                label = format_twilio_price(value)
            else:
                label = "" if value is None else str(value)
            items.append(TwilioFacetItem(value=label, count=int(cnt)))
        return TwilioFacetResponse(column=column, items=items, truncated=truncated)

    def write_xlsx(
        self,
        path: str | Path,
        *,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ) -> int:
        wb = open_styled_workbook(str(path), constant_memory=True)
        written = 0
        try:
            ws = wb.add_worksheet(TWILIO_XLSX_SHEET)
            writer = StyledSheetWriter(wb, ws, TWILIO_XLSX_HEADERS)
            for row in self.iter_coverage(
                sort_by=sort_by,
                sort_dir=sort_dir,
                filters=filters,
                q=q,
            ):
                writer.write_row(
                    [
                        row.country_name or "",
                        row.country_iso or "",
                        row.number_type or "",
                        format_twilio_price(row.period_price),
                        row.price_unit or "",
                        BOOL_TRUE if row.country_beta else BOOL_FALSE if row.country_beta is False else "",
                    ]
                )
                written += 1
            writer.finalize()
        finally:
            wb.close()
        return written


TWILIO_NUMBERS_XLSX_SHEET = "twilio-numbers"
TWILIO_NUMBERS_XLSX_HEADERS = [
    "Страна",
    "Номер",
    "Тип",
    "Регион",
    "Город",
    "Абонплата",
    "Voice",
    "SMS",
    "MMS",
    "Fax",
    "Адрес",
]


class TwilioNumbersService:
    TEXT_COLUMNS: dict[str, Any] = {
        "country_name": TwilioAvailableNumber.country_name,
        "phone_number": TwilioAvailableNumber.phone_number,
        "number_type": TwilioAvailableNumber.number_type,
        "region": TwilioAvailableNumber.region,
        "locality": TwilioAvailableNumber.locality,
        "address_requirements": TwilioAvailableNumber.address_requirements,
    }
    PRICE_COLUMNS = {
        "period_price": TwilioCatalog.period_price,
    }
    BOOL_COLUMNS = {
        "voice": TwilioAvailableNumber.voice,
        "sms": TwilioAvailableNumber.sms,
        "mms": TwilioAvailableNumber.mms,
        "fax": TwilioAvailableNumber.fax,
    }
    FACET_COLUMNS = frozenset(set(TEXT_COLUMNS) | set(PRICE_COLUMNS) | set(BOOL_COLUMNS))
    SORTABLE = {
        "country_name": TwilioAvailableNumber.country_name,
        "phone_number": TwilioAvailableNumber.phone_number,
        "number_type": TwilioAvailableNumber.number_type,
        "region": TwilioAvailableNumber.region,
        "locality": TwilioAvailableNumber.locality,
        "period_price": TwilioCatalog.period_price,
        "voice": TwilioAvailableNumber.voice,
        "sms": TwilioAvailableNumber.sms,
        "mms": TwilioAvailableNumber.mms,
        "fax": TwilioAvailableNumber.fax,
        "address_requirements": TwilioAvailableNumber.address_requirements,
    }

    def __init__(self, db: Session):
        self.db = db

    parse_filters = staticmethod(TwilioCatalogService.parse_filters)

    def _base(self) -> Select:
        return (
            select(TwilioAvailableNumber, TwilioCatalog.period_price, TwilioCatalog.price_unit)
            .select_from(TwilioAvailableNumber)
            .outerjoin(
                TwilioCatalog,
                and_(
                    TwilioCatalog.provider_id == TwilioAvailableNumber.provider_id,
                    TwilioCatalog.country_iso == TwilioAvailableNumber.country_iso,
                    TwilioCatalog.number_type == TwilioAvailableNumber.number_type,
                    TwilioCatalog.is_currently_present.is_(True),
                ),
            )
        )

    def _empty_pred(self, col: ColumnElement[Any]) -> ColumnElement[Any]:
        return or_(col.is_(None), cast(col, String) == "")

    def _apply_filters(
        self,
        stmt: Select,
        filters: dict[str, list[str]],
        *,
        q: str | None = None,
        exclude_column: str | None = None,
    ) -> Select:
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    TwilioAvailableNumber.country_name.ilike(like),
                    TwilioAvailableNumber.country_iso.ilike(like),
                    TwilioAvailableNumber.phone_number.ilike(like),
                    TwilioAvailableNumber.number_type.ilike(like),
                    TwilioAvailableNumber.region.ilike(like),
                    TwilioAvailableNumber.locality.ilike(like),
                )
            )
        for field, values in filters.items():
            if field == exclude_column or field not in self.FACET_COLUMNS or not values:
                continue
            include_empty = EMPTY_TOKEN in values or "" in values
            concrete = [v for v in values if v not in (EMPTY_TOKEN, "")]
            preds: list[Any] = []
            if field in self.PRICE_COLUMNS:
                col = self.PRICE_COLUMNS[field]
                nums = [n for n in (_parse_price_token(v) for v in concrete) if n is not None]
                if nums:
                    preds.append(col.in_(nums))
                if include_empty:
                    preds.append(col.is_(None))
            elif field in self.BOOL_COLUMNS:
                col = self.BOOL_COLUMNS[field]
                wanted: list[bool] = []
                for v in concrete:
                    if v == BOOL_TRUE:
                        wanted.append(True)
                    elif v == BOOL_FALSE:
                        wanted.append(False)
                if wanted:
                    preds.append(col.in_(wanted))
                if include_empty:
                    preds.append(col.is_(None))
            else:
                col = self.TEXT_COLUMNS[field]
                if concrete:
                    preds.append(col.in_(concrete))
                if include_empty:
                    preds.append(self._empty_pred(col))
            if preds:
                stmt = stmt.where(or_(*preds) if len(preds) > 1 else preds[0])
        return stmt

    def _to_item(self, row: TwilioAvailableNumber, period_price: Any, price_unit: Any) -> TwilioNumberItem:
        return TwilioNumberItem(
            id=row.id,
            phone_number=row.phone_number,
            country_name=row.country_name,
            country_iso=row.country_iso,
            number_type=row.number_type,
            region=row.region,
            locality=row.locality,
            period_price=period_price,
            price_unit=price_unit,
            voice=row.voice,
            sms=row.sms,
            mms=row.mms,
            fax=row.fax,
            address_requirements=row.address_requirements,
        )

    def list_numbers(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ) -> Page[TwilioNumberItem]:
        stmt = self._apply_filters(self._base(), filters, q=q)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        col = self.SORTABLE.get(sort_by or "", TwilioAvailableNumber.country_name)
        order = col.asc() if sort_dir != "desc" else col.desc()
        rows = self.db.execute(
            stmt.order_by(order, TwilioAvailableNumber.phone_number.asc(), TwilioAvailableNumber.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return Page.of(
            [self._to_item(number, price, unit) for number, price, unit in rows],
            page=page,
            page_size=page_size,
            total=int(total),
        )

    def iter_numbers(
        self,
        *,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ):
        stmt = self._apply_filters(self._base(), filters, q=q)
        col = self.SORTABLE.get(sort_by or "", TwilioAvailableNumber.country_name)
        order = col.asc() if sort_dir != "desc" else col.desc()
        yield from self.db.execute(
            stmt.order_by(order, TwilioAvailableNumber.phone_number.asc(), TwilioAvailableNumber.id.asc())
        )

    def _facet_value_expr(self, column: str) -> ColumnElement[Any]:
        if column in self.PRICE_COLUMNS:
            return self.PRICE_COLUMNS[column]
        if column in self.BOOL_COLUMNS:
            col = self.BOOL_COLUMNS[column]
            return case((col.is_(True), BOOL_TRUE), (col.is_(False), BOOL_FALSE), else_=None)
        return func.nullif(func.btrim(cast(self.TEXT_COLUMNS[column], String)), "")

    def list_facets(
        self,
        *,
        column: str,
        filters: dict[str, list[str]],
        q: str | None,
        value_q: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> TwilioFacetResponse:
        if column not in self.FACET_COLUMNS:
            raise ValueError(f"Unknown facet column: {column}")
        stmt = self._apply_filters(self._base(), filters, q=q, exclude_column=column)
        base = (
            stmt.with_only_columns(
                self._facet_value_expr(column).label("facet_value"),
                TwilioAvailableNumber.id.label("row_id"),
            )
            .order_by(None)
            .subquery()
        )
        grouped = select(base.c.facet_value, func.count().label("cnt")).group_by(
            base.c.facet_value
        )
        if value_q:
            grouped = grouped.where(cast(base.c.facet_value, String).ilike(f"%{value_q}%"))
        numeric_facet = column in self.PRICE_COLUMNS
        tie_break = base.c.facet_value if numeric_facet else cast(base.c.facet_value, String)
        grouped = grouped.order_by(func.count().desc(), tie_break.asc().nulls_last())
        rows = self.db.execute(grouped.offset(offset).limit(limit + 1)).all()
        truncated = len(rows) > limit
        items = []
        for value, cnt in rows[:limit]:
            if column in self.PRICE_COLUMNS:
                label = format_twilio_price(value)
            else:
                label = "" if value is None else str(value)
            items.append(TwilioFacetItem(value=label, count=int(cnt)))
        return TwilioFacetResponse(column=column, items=items, truncated=truncated)

    def write_xlsx(
        self,
        path: str | Path,
        *,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ) -> int:
        wb = open_styled_workbook(str(path), constant_memory=True)
        written = 0
        try:
            ws = wb.add_worksheet(TWILIO_NUMBERS_XLSX_SHEET)
            writer = StyledSheetWriter(wb, ws, TWILIO_NUMBERS_XLSX_HEADERS)
            for number, price, _unit in self.iter_numbers(
                sort_by=sort_by,
                sort_dir=sort_dir,
                filters=filters,
                q=q,
            ):
                writer.write_row(
                    [
                        number.country_name or "",
                        number.phone_number or "",
                        number.number_type or "",
                        number.region or "",
                        number.locality or "",
                        format_twilio_price(price),
                        BOOL_TRUE if number.voice else BOOL_FALSE if number.voice is False else "",
                        BOOL_TRUE if number.sms else BOOL_FALSE if number.sms is False else "",
                        BOOL_TRUE if number.mms else BOOL_FALSE if number.mms is False else "",
                        BOOL_TRUE if number.fax else BOOL_FALSE if number.fax is False else "",
                        number.address_requirements or "",
                    ]
                )
                written += 1
            writer.finalize()
        finally:
            wb.close()
        return written
