from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.mask_types import MaskType
from app.modules.catalog.apply_mask_types import normalize_key_part
from app.modules.catalog.beauty_mask import all_beauty_masks, canonical_beauty_masks
from app.schemas.mask_types import MaskTypeItem, MaskTypesLoadResult
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook

MASK_TYPES_XLSX_HEADERS = (
    "Разрядность",
    "Категория",
    "ABC",
    "Маска",
    "Тип",
    "Премиум",
    "Покупка",
    "Абонплата",
)
MASK_TYPES_XLSX_HEADERS_V7 = MASK_TYPES_XLSX_HEADERS[:7]
MASK_TYPES_XLSX_SHEET = "Маски"
MAX_IMPORT_BYTES = 5 * 1024 * 1024
EXPECTED_SEED_COUNT = 5220


@dataclass(frozen=True)
class MaskTypeImportRow:
    digit_capacity: str
    category: str
    abc: str
    mask: str
    type_label: str | None
    premium: Decimal | None
    purchase: Decimal | None
    period: Decimal | None


def _cell_text(value: object) -> str:
    return normalize_key_part(value)


def _nullable_cell(value: object) -> str | None:
    text = _cell_text(value)
    return text or None


def _row_empty(values: list[object]) -> bool:
    return all(_cell_text(v) == "" for v in values)


def _parse_price_cell(value: object, *, row: int, column: str) -> Decimal | None:
    if isinstance(value, bool):
        raise ValueError(f"Строка {row}: некорректная цена в столбце {column}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    text = _cell_text(value).replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Строка {row}: некорректная цена в столбце {column}") from exc


def _xlsx_price(value: Decimal | None) -> object:
    if value is None:
        return ""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def parse_mask_types_xlsx(data: bytes) -> list[MaskTypeImportRow]:
    if not data:
        raise ValueError("Пустой файл")
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("Файл слишком большой")
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("Не удалось прочитать XLSX") from exc
    try:
        if not wb.worksheets:
            raise ValueError("В файле нет листов")
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration as exc:
            raise ValueError("Нет заголовков") from exc
        header_cells = list(header or ())
        got7 = tuple(_cell_text(c) for c in header_cells[:7])
        got8 = tuple(_cell_text(c) for c in header_cells[:8])
        if got8 == MASK_TYPES_XLSX_HEADERS:
            width = 8
        elif got7 == MASK_TYPES_XLSX_HEADERS_V7:
            width = 7
        else:
            raise ValueError(
                "Заголовки должны быть: Разрядность, Категория, ABC, Маска, Тип, Премиум, Покупка, Абонплата"
            )
        canonical = canonical_beauty_masks()
        out: list[MaskTypeImportRow] = []
        seen: set[tuple[str, str, str, str]] = set()
        for idx, raw in enumerate(rows_iter, start=2):
            cells = list(raw or ())
            while len(cells) < width:
                cells.append(None)
            chunk = cells[:width]
            if _row_empty(chunk):
                continue
            cap = _cell_text(chunk[0])
            category = _cell_text(chunk[1])
            abc = _cell_text(chunk[2])
            mask = _cell_text(chunk[3])
            if not mask:
                raise ValueError(f"Строка {idx}: не указана маска")
            if mask not in canonical:
                raise ValueError(f"Строка {idx}: неизвестная маска {mask}")
            key = (cap, category, abc, mask)
            if key in seen:
                raise ValueError(
                    f"Строка {idx}: повторяется комбинация разрядность/категория/ABC/маска"
                )
            seen.add(key)
            period = (
                _parse_price_cell(chunk[7], row=idx, column="Абонплата")
                if width == 8
                else None
            )
            out.append(
                MaskTypeImportRow(
                    digit_capacity=cap,
                    category=category,
                    abc=abc,
                    mask=mask,
                    type_label=_nullable_cell(chunk[4]),
                    premium=_parse_price_cell(chunk[5], row=idx, column="Премиум"),
                    purchase=_parse_price_cell(chunk[6], row=idx, column="Покупка"),
                    period=period,
                )
            )
        return out
    finally:
        wb.close()


def ensure_mask_types_seeded(db: Session) -> int:
    seed_count = db.scalar(
        select(func.count())
        .select_from(MaskType)
        .where(
            MaskType.digit_capacity == "",
            MaskType.category == "",
            MaskType.abc == "",
        )
    )
    if int(seed_count or 0) >= EXPECTED_SEED_COUNT:
        return 0
    existing = set(
        db.scalars(
            select(MaskType.mask).where(
                MaskType.digit_capacity == "",
                MaskType.category == "",
                MaskType.abc == "",
            )
        ).all()
    )
    missing = [mask for mask in all_beauty_masks() if mask not in existing]
    if not missing:
        return 0
    db.add_all(
        [
            MaskType(
                id=uuid4(),
                digit_capacity="",
                category="",
                abc="",
                mask=mask,
            )
            for mask in missing
        ]
    )
    db.commit()
    return len(missing)


class MaskTypesService:
    def __init__(self, db: Session):
        self.db = db

    def list_items(self) -> list[MaskTypeItem]:
        ensure_mask_types_seeded(self.db)
        rows = self.db.scalars(
            select(MaskType).order_by(
                MaskType.mask.asc(),
                MaskType.digit_capacity.asc(),
                MaskType.category.asc(),
                MaskType.abc.asc(),
            )
        ).all()
        return [
            MaskTypeItem(
                id=row.id,
                digit_capacity=row.digit_capacity,
                category=row.category,
                abc=row.abc,
                mask=row.mask,
                type_label=row.type_label,
                premium=row.premium,
                purchase=row.purchase,
                period=row.period,
            )
            for row in rows
        ]

    def write_xlsx(self, path: str | Path) -> int:
        items = self.list_items()
        wb = open_styled_workbook(str(path), constant_memory=True)
        try:
            ws = wb.add_worksheet(MASK_TYPES_XLSX_SHEET)
            writer = StyledSheetWriter(wb, ws, MASK_TYPES_XLSX_HEADERS)
            for item in items:
                writer.write_row(
                    [
                        item.digit_capacity,
                        item.category,
                        item.abc,
                        item.mask,
                        item.type_label or "",
                        _xlsx_price(item.premium),
                        _xlsx_price(item.purchase),
                        _xlsx_price(item.period),
                    ]
                )
            writer.finalize()
        finally:
            wb.close()
        return len(items)

    def upsert_from_xlsx(self, data: bytes) -> MaskTypesLoadResult:
        ensure_mask_types_seeded(self.db)
        parsed = parse_mask_types_xlsx(data)
        existing_rows = self.db.scalars(select(MaskType)).all()
        by_key = {
            (row.digit_capacity, row.category, row.abc, row.mask): row
            for row in existing_rows
        }
        inserted = 0
        updated = 0
        for item in parsed:
            key = (item.digit_capacity, item.category, item.abc, item.mask)
            row = by_key.get(key)
            if row is None:
                row = MaskType(
                    id=uuid4(),
                    digit_capacity=item.digit_capacity,
                    category=item.category,
                    abc=item.abc,
                    mask=item.mask,
                    type_label=item.type_label,
                    premium=item.premium,
                    purchase=item.purchase,
                    period=item.period,
                )
                self.db.add(row)
                by_key[key] = row
                inserted += 1
                continue
            row.type_label = item.type_label
            row.premium = item.premium
            row.purchase = item.purchase
            row.period = item.period
            updated += 1
        self.db.commit()
        return MaskTypesLoadResult(
            ok=True,
            count=len(parsed),
            updated=updated,
            inserted=inserted,
            message=f"Обновлено: {updated}, добавлено: {inserted}",
        )
