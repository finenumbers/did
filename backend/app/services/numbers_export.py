"""XLSX export of filtered numbers catalog (xlsxwriter, constant_memory)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.catalog import NumbersCatalogNormalized
from app.models.enums import InventoryKind
from app.services.numbers_service import NumbersService
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook

# UI column order / Russian headers (matches NumbersTable)
EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("provider_code", "Провайдер"),
    ("abc_code", "ABC"),
    ("number_local", "Номер"),
    ("number_category", "Категория"),
    ("status_raw", "Статус"),
    ("region_name", "Регион"),
    ("city_name", "Город"),
    ("buy_price", "Покупка"),
    ("period_price", "Абонплата"),
    ("mask", "Маска"),
    ("display_mask", "Display mask"),
    ("book_date", "Book date"),
    ("number_type", "Тип"),
    ("points", "Баллы"),
    ("date_from", "date_from"),
    ("last_operation_date", "last_operation_date"),
    ("operator", "Оператор"),
    ("rtu_connected", "Подключено в РТУ"),
    ("operator_id", "operator_id"),
    ("manager_id", "manager_id"),
    ("notes", "notes"),
    ("abcdef", "abcdef"),
    ("order_id", "order_id"),
    ("doc_status", "doc_status"),
    ("doc_required", "doc_required"),
    ("order_doc_required", "order_doc_required"),
    ("sign", "sign"),
    ("tariff", "Тариф"),
    ("class", "Класс"),
    ("partner", "Партнёр"),
    ("project", "Проект"),
    ("equipment", "Оборудование"),
    ("mapping_confidence", "confidence"),
    ("last_seen_at", "Обновлено"),
]

RTU_NOT_CONNECTED_FILL = "#FFC7CE"
RTU_EXTERNAL_FILL = "#FFEB9C"

_BATCH = 5_000
DEFAULT_SORT_BY = "abc_code"
DEFAULT_SORT_DIR = "asc"

ProgressCb = Callable[[int, int | None], None]


def _format_price(value: Any) -> str:
    if value is None or value == "":
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


def _format_points(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _cell_value(key: str, row: NumbersCatalogNormalized, provider_code: str) -> Any:
    if key == "provider_code":
        return provider_code
    if key == "class":
        return row.number_class or ""
    if key == "buy_price":
        return _format_price(row.buy_price)
    if key == "period_price":
        return _format_price(row.period_price)
    if key == "points":
        return _format_points(row.points)
    if key == "mapping_confidence":
        conf = row.mapping_confidence
        return conf.value if hasattr(conf, "value") else (str(conf) if conf else "")
    if key == "last_seen_at":
        ts = row.last_seen_at
        if isinstance(ts, datetime):
            return ts.isoformat()
        return str(ts) if ts else ""
    val = getattr(row, key, None)
    return "" if val is None else val


def is_default_export_query(
    *,
    filters: dict[str, list[str]] | None,
    number_local_q: str | None,
    sort_by: str | None,
    sort_dir: str,
) -> bool:
    if filters:
        return False
    if (number_local_q or "").strip():
        return False
    sb = (sort_by or DEFAULT_SORT_BY).strip() or DEFAULT_SORT_BY
    sd = (sort_dir or DEFAULT_SORT_DIR).strip().lower() or DEFAULT_SORT_DIR
    return sb == DEFAULT_SORT_BY and sd == DEFAULT_SORT_DIR


def catalog_fingerprint(db: Session, inventory_kind: InventoryKind) -> dict[str, Any]:
    count, max_seen = db.execute(
        select(
            func.count(),
            func.max(NumbersCatalogNormalized.last_seen_at),
        ).where(
            NumbersCatalogNormalized.inventory_kind == inventory_kind,
            NumbersCatalogNormalized.is_currently_present.is_(True),
        )
    ).one()
    max_iso = max_seen.isoformat() if isinstance(max_seen, datetime) else None
    return {"count": int(count or 0), "max_last_seen_at": max_iso}


class NumbersExportService:
    def __init__(self, db: Session):
        self.db = db
        self.numbers = NumbersService(db)

    def count_filtered(
        self,
        *,
        inventory_kind: InventoryKind,
        filters: dict[str, list[str]] | None = None,
        number_local_q: str | None = None,
    ) -> int:
        stmt = self.numbers._base_stmt(inventory_kind, is_currently_present=True)
        stmt = self.numbers.apply_catalog_filters(
            stmt,
            filters=filters,
            number_local_q=number_local_q,
        )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        return int(self.db.scalar(count_stmt) or 0)

    def export_xlsx(
        self,
        *,
        inventory_kind: InventoryKind,
        path: str | Path,
        filters: dict[str, list[str]] | None = None,
        number_local_q: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        on_progress: ProgressCb | None = None,
        rows_total: int | None = None,
    ) -> int:
        """Write filtered catalog to path. Returns data row count (excluding header)."""
        stmt = self.numbers._base_stmt(inventory_kind, is_currently_present=True)
        stmt = self.numbers.apply_catalog_filters(
            stmt,
            filters=filters,
            number_local_q=number_local_q,
        )
        stmt = stmt.order_by(*self.numbers.order_by_clauses(sort_by, sort_dir))

        if rows_total is None:
            rows_total = self.count_filtered(
                inventory_kind=inventory_kind,
                filters=filters,
                number_local_q=number_local_q,
            )

        sheet_title = "Свободные" if inventory_kind == InventoryKind.free else "Купленные"
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        workbook = open_styled_workbook(str(out), constant_memory=True)
        ws = workbook.add_worksheet(sheet_title[:31])
        columns = [
            (k, h)
            for k, h in EXPORT_COLUMNS
            if inventory_kind == InventoryKind.purchased or k != "rtu_connected"
        ]
        headers = [header for _, header in columns]
        keys = [key for key, _ in columns]
        writer = StyledSheetWriter(workbook, ws, headers)

        row_count = 0
        result = self.db.execute(stmt.execution_options(yield_per=_BATCH))
        try:
            for row, code in result:
                provider_code = code.value if hasattr(code, "value") else str(code)
                fill = None
                if inventory_kind == InventoryKind.purchased:
                    rtu = row.rtu_connected or ""
                    if rtu == "Не подключено":
                        fill = RTU_NOT_CONNECTED_FILL
                    elif rtu == "Внешняя нумерация":
                        fill = RTU_EXTERNAL_FILL
                writer.write_row(
                    [_cell_value(key, row, provider_code) for key in keys],
                    fill_color=fill,
                )
                row_count += 1
                if on_progress and row_count % _BATCH == 0:
                    on_progress(row_count, rows_total)
            writer.finalize()
        finally:
            workbook.close()

        if on_progress:
            on_progress(row_count, rows_total)
        return row_count


def export_xlsx_job(
    *,
    inventory_kind: InventoryKind,
    path: str,
    filters: dict[str, list[str]] | None,
    number_local_q: str | None,
    sort_by: str | None,
    sort_dir: str,
    on_progress: ProgressCb | None = None,
    rows_total: int | None = None,
) -> int:
    """Run export in a dedicated DB session (safe for worker threads)."""
    db = SessionLocal()
    try:
        return NumbersExportService(db).export_xlsx(
            inventory_kind=inventory_kind,
            path=path,
            filters=filters,
            number_local_q=number_local_q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            on_progress=on_progress,
            rows_total=rows_total,
        )
    finally:
        db.close()
