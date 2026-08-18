"""XLSX export of filtered numbers catalog (xlsxwriter, constant_memory)."""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

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
    ("city_name", "Город"),
    ("region_name", "Регион"),
    ("operator", "Оператор"),
    ("buy_price", "Покупка (Входящая)"),
    ("period_price", "Абонплата (Входящая)"),
    ("mask_purchase", "Покупка"),
    ("type_label", "Тип"),
    ("premium", "Премиум"),
    ("rtu_connected", "Подключено в РТУ"),
]

RTU_NOT_CONNECTED_FILL = "#FFC7CE"
RTU_EXTERNAL_FILL = "#FFEB9C"
OPERATOR_NOT_IN_REGISTRY_FILL = "#BDD7EE"

_BATCH = 5_000
_PROGRESS_EVERY_ROWS = 1_000
_PROGRESS_EVERY_SEC = 0.5
DEFAULT_SORT_BY = "abc_code"
DEFAULT_SORT_DIR = "asc"

# Header-based widths for catalog export (no per-cell display_len).
_HEADER_MIN_CHARS: dict[str, int] = {
    "Провайдер": 14,
    "ABC": 8,
    "Номер": 12,
    "Категория": 12,
    "Город": 16,
    "Регион": 18,
    "Оператор": 18,
    "Покупка (Входящая)": 18,
    "Абонплата (Входящая)": 20,
    "Покупка": 10,
    "Тип": 12,
    "Премиум": 12,
    "Подключено в РТУ": 18,
}

_EXPORT_LOAD_ONLY = (
    NumbersCatalogNormalized.provider_id,
    NumbersCatalogNormalized.abc_code,
    NumbersCatalogNormalized.number_local,
    NumbersCatalogNormalized.number_category,
    NumbersCatalogNormalized.city_name,
    NumbersCatalogNormalized.region_name,
    NumbersCatalogNormalized.operator,
    NumbersCatalogNormalized.buy_price,
    NumbersCatalogNormalized.period_price,
    NumbersCatalogNormalized.mask_purchase,
    NumbersCatalogNormalized.type_label,
    NumbersCatalogNormalized.premium,
    NumbersCatalogNormalized.rtu_connected,
)

ProgressCb = Callable[..., None]


def _call_progress(
    on_progress: ProgressCb | None,
    done: int,
    tot: int | None,
    phase: str,
) -> None:
    if on_progress is None:
        return
    try:
        on_progress(done, tot, phase)
    except TypeError:
        on_progress(done, tot)


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


_PRICE_EXPORT_KEYS = frozenset(
    {"buy_price", "period_price", "mask_purchase", "premium"}
)


def _cell_value(key: str, row: NumbersCatalogNormalized, provider_code: str) -> Any:
    if key == "provider_code":
        return provider_code
    if key in _PRICE_EXPORT_KEYS:
        return _format_price(getattr(row, key, None))
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


def _iso_dt(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def export_columns_schema() -> str:
    return "|".join(header for _key, header in EXPORT_COLUMNS)


def catalog_fingerprint(db: Session, inventory_kind: InventoryKind) -> dict[str, Any]:
    count, max_seen, max_updated = db.execute(
        select(
            func.count(),
            func.max(NumbersCatalogNormalized.last_seen_at),
            func.max(NumbersCatalogNormalized.updated_at),
        ).where(
            NumbersCatalogNormalized.inventory_kind == inventory_kind,
            NumbersCatalogNormalized.is_currently_present.is_(True),
        )
    ).one()
    return {
        "count": int(count or 0),
        "max_last_seen_at": _iso_dt(max_seen),
        "max_updated_at": _iso_dt(max_updated),
        "columns_schema": export_columns_schema(),
    }


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
        stmt = stmt.options(load_only(*_EXPORT_LOAD_ONLY))

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
        writer = StyledSheetWriter(
            workbook,
            ws,
            headers,
            track_content_width=False,
            min_chars=[_HEADER_MIN_CHARS.get(h, 12) for h in headers],
        )

        row_count = 0
        last_progress_t = time.monotonic()
        last_progress_n = 0

        def maybe_progress(*, force: bool = False, phase: str = "writing") -> None:
            nonlocal last_progress_t, last_progress_n
            now = time.monotonic()
            if (
                force
                or row_count - last_progress_n >= _PROGRESS_EVERY_ROWS
                or now - last_progress_t >= _PROGRESS_EVERY_SEC
            ):
                _call_progress(on_progress, row_count, rows_total, phase)
                last_progress_t = now
                last_progress_n = row_count

        result = self.db.execute(stmt.execution_options(yield_per=_BATCH))
        try:
            for row, code in result:
                provider_code = code.value if hasattr(code, "value") else str(code)
                fill = None
                if (row.operator or "") == "Нет в реестре":
                    fill = OPERATOR_NOT_IN_REGISTRY_FILL
                elif inventory_kind == InventoryKind.purchased:
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
                maybe_progress()
            writer.finalize()
            _call_progress(on_progress, row_count, rows_total, "closing")
        finally:
            workbook.close()

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
