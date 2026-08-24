from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import Select, case, cast, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement
from sqlalchemy.types import String

from app.models.didww import DidwwCatalog
from app.schemas.common import Page
from app.schemas.didww import DidwwFacetItem, DidwwFacetResponse, DidwwGroupItem
from app.services.numbers_service import EMPTY_TOKEN, _parse_price_token
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook

BOOL_TRUE = "да"
BOOL_FALSE = "нет"

DIDWW_FEATURE_FLAGS = (
    "voice_in",
    "voice_out",
    "t38",
    "sms_in",
    "p2p",
    "a2p",
    "emergency",
    "cnam_out",
)

# DIDWW SKU prices are fractions of a dollar ("0.0", "0.3", "0.8"), so the integer
# ruble formatting used by the RU catalog would collapse them all to 0 or 1.
PRICE_SCALE = 4

DIDWW_XLSX_SHEET = "didww"
DIDWW_XLSX_HEADERS = [
    "Страна",
    "ISO",
    "Код страны",
    "Регион",
    "Город",
    "Префикс",
    "Тип",
    "Покупка",
    "Абонплата",
    "Каналы",
    "В наличии",
    "Выбор номера",
    *DIDWW_FEATURE_FLAGS,
    "Регистрация",
    "Поминутно",
]


def features_has(features: str | None, flag: str) -> bool:
    if not features:
        return False
    return flag in {part.strip() for part in features.split(",") if part.strip()}


def _packed_features_expr() -> ColumnElement[Any]:
    return func.concat(",", func.replace(func.coalesce(DidwwCatalog.features, ""), " ", ""), ",")


def _feature_present_expr(flag: str) -> ColumnElement[Any]:
    return _packed_features_expr().like(f"%,{flag},%")


def _as_bool_label(value: bool | None) -> str:
    if value is None:
        return ""
    return BOOL_TRUE if value else BOOL_FALSE


def format_didww_price(value: Any) -> str:
    """Keep the stored precision, drop trailing zeros: 0.3000 -> "0.3", 12.0000 -> "12"."""
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value)).quantize(Decimal(1).scaleb(-PRICE_SCALE))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    sign = "-" if amount < 0 else ""
    whole, _, fraction = format(abs(amount).normalize(), "f").partition(".")
    groups: list[str] = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    grouped = " ".join(reversed(groups)) or "0"
    return sign + (f"{grouped}.{fraction}" if fraction else grouped)


class DidwwCatalogService:
    TEXT_COLUMNS: dict[str, Any] = {
        "country_name": DidwwCatalog.country_name,
        "country_iso": DidwwCatalog.country_iso,
        "country_prefix": DidwwCatalog.country_prefix,
        "region_name": DidwwCatalog.region_name,
        "city_name": DidwwCatalog.city_name,
        "area_prefix": DidwwCatalog.area_prefix,
        "did_type": DidwwCatalog.did_type,
    }
    PRICE_COLUMNS = {
        "buy_price": DidwwCatalog.buy_price,
        "period_price": DidwwCatalog.period_price,
    }
    BOOL_COLUMNS = {
        "number_select": DidwwCatalog.number_select,
        "needs_registration": DidwwCatalog.needs_registration,
        "is_metered": DidwwCatalog.is_metered,
    }
    FEATURE_FLAG_COLUMNS = {flag: _feature_present_expr(flag) for flag in DIDWW_FEATURE_FLAGS}
    INT_COLUMNS = {
        "channels_included": DidwwCatalog.channels_included,
        "stock_count": DidwwCatalog.stock_count,
    }
    FACET_COLUMNS = frozenset(
        set(TEXT_COLUMNS)
        | set(PRICE_COLUMNS)
        | set(BOOL_COLUMNS)
        | set(FEATURE_FLAG_COLUMNS)
        | set(INT_COLUMNS)
    )
    SORTABLE = {
        "country_name": DidwwCatalog.country_name,
        "country_iso": DidwwCatalog.country_iso,
        "country_prefix": DidwwCatalog.country_prefix,
        "region_name": DidwwCatalog.region_name,
        "city_name": DidwwCatalog.city_name,
        "area_prefix": DidwwCatalog.area_prefix,
        "did_type": DidwwCatalog.did_type,
        "buy_price": DidwwCatalog.buy_price,
        "period_price": DidwwCatalog.period_price,
        "channels_included": DidwwCatalog.channels_included,
        "stock_count": DidwwCatalog.stock_count,
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
        return select(DidwwCatalog).where(DidwwCatalog.is_currently_present.is_(True))

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
                    DidwwCatalog.country_name.ilike(like),
                    DidwwCatalog.country_iso.ilike(like),
                    DidwwCatalog.city_name.ilike(like),
                    DidwwCatalog.region_name.ilike(like),
                    DidwwCatalog.area_prefix.ilike(like),
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
            elif field in self.FEATURE_FLAG_COLUMNS:
                expr = self.FEATURE_FLAG_COLUMNS[field]
                wanted_true = BOOL_TRUE in concrete
                wanted_false = BOOL_FALSE in concrete
                if wanted_true and not wanted_false:
                    preds.append(expr)
                elif wanted_false and not wanted_true:
                    preds.append(~expr)
            elif field in self.INT_COLUMNS:
                col = self.INT_COLUMNS[field]
                ints: list[int] = []
                for v in concrete:
                    try:
                        ints.append(int(v))
                    except ValueError:
                        continue
                if ints:
                    preds.append(col.in_(ints))
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

    def list_groups(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ) -> Page[DidwwGroupItem]:
        stmt = self._apply_filters(self._base(), filters, q=q)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        col = self.SORTABLE.get(sort_by or "", DidwwCatalog.country_name)
        order = col.asc() if sort_dir != "desc" else col.desc()
        rows = self.db.scalars(
            stmt.order_by(order, DidwwCatalog.area_prefix.asc(), DidwwCatalog.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return Page.of(
            [DidwwGroupItem.model_validate(r) for r in rows],
            page=page,
            page_size=page_size,
            total=int(total),
        )

    def iter_groups(
        self,
        *,
        sort_by: str | None,
        sort_dir: str,
        filters: dict[str, list[str]],
        q: str | None,
    ):
        stmt = self._apply_filters(self._base(), filters, q=q)
        col = self.SORTABLE.get(sort_by or "", DidwwCatalog.country_name)
        order = col.asc() if sort_dir != "desc" else col.desc()
        yield from self.db.scalars(stmt.order_by(order, DidwwCatalog.area_prefix.asc(), DidwwCatalog.id.asc()))

    def _facet_value_expr(self, column: str) -> ColumnElement[Any]:
        if column in self.PRICE_COLUMNS:
            # Exact stored amount: rounding would merge 0.3 and 0.8 into one bucket.
            return self.PRICE_COLUMNS[column]
        if column in self.BOOL_COLUMNS:
            col = self.BOOL_COLUMNS[column]
            return case((col.is_(True), BOOL_TRUE), (col.is_(False), BOOL_FALSE), else_=None)
        if column in self.FEATURE_FLAG_COLUMNS:
            return case((self.FEATURE_FLAG_COLUMNS[column], BOOL_TRUE), else_=BOOL_FALSE)
        if column in self.INT_COLUMNS:
            return self.INT_COLUMNS[column]
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
    ) -> DidwwFacetResponse:
        if column not in self.FACET_COLUMNS:
            raise ValueError(f"Unknown facet column: {column}")
        stmt = self._apply_filters(self._base(), filters, q=q, exclude_column=column)
        base = (
            stmt.with_only_columns(
                self._facet_value_expr(column).label("facet_value"),
                DidwwCatalog.id.label("row_id"),
            )
            .order_by(None)
            .subquery()
        )
        grouped = select(base.c.facet_value, func.count().label("cnt")).group_by(
            base.c.facet_value
        )
        if value_q:
            grouped = grouped.where(cast(base.c.facet_value, String).ilike(f"%{value_q}%"))
        numeric_facet = column in self.PRICE_COLUMNS or column in self.INT_COLUMNS
        tie_break = (
            base.c.facet_value if numeric_facet else cast(base.c.facet_value, String)
        )
        grouped = grouped.order_by(func.count().desc(), tie_break.asc().nulls_last())
        rows = self.db.execute(grouped.offset(offset).limit(limit + 1)).all()
        truncated = len(rows) > limit
        items = []
        for value, cnt in rows[:limit]:
            if column in self.PRICE_COLUMNS:
                label = format_didww_price(value)
            else:
                label = "" if value is None else str(value)
            items.append(DidwwFacetItem(value=label, count=int(cnt)))
        return DidwwFacetResponse(column=column, items=items, truncated=truncated)

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
            ws = wb.add_worksheet(DIDWW_XLSX_SHEET)
            writer = StyledSheetWriter(wb, ws, DIDWW_XLSX_HEADERS)
            for row in self.iter_groups(
                sort_by=sort_by,
                sort_dir=sort_dir,
                filters=filters,
                q=q,
            ):
                writer.write_row(
                    [
                        row.country_name or "",
                        row.country_iso or "",
                        row.country_prefix or "",
                        row.region_name or "",
                        row.city_name or "",
                        row.area_prefix or "",
                        row.did_type or "",
                        format_didww_price(row.buy_price),
                        format_didww_price(row.period_price),
                        row.channels_included if row.channels_included is not None else "",
                        row.stock_count if row.stock_count is not None else "",
                        _as_bool_label(row.number_select),
                        *[
                            _as_bool_label(features_has(row.features, flag))
                            for flag in DIDWW_FEATURE_FLAGS
                        ],
                        _as_bool_label(row.needs_registration),
                        _as_bool_label(row.is_metered),
                    ]
                )
                written += 1
            writer.finalize()
        finally:
            wb.close()
        return written
