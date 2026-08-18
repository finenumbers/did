from __future__ import annotations

from dataclasses import dataclass
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
)
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
    premium: str | None
    purchase: str | None


def _cell_text(value: object) -> str:
    return normalize_key_part(value)


def _nullable_cell(value: object) -> str | None:
    text = _cell_text(value)
    return text or None


def _row_empty(values: list[object]) -> bool:
    return all(_cell_text(v) == "" for v in values)


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
        got = tuple(_cell_text(c) for c in list(header or ())[:7])
        if got != MASK_TYPES_XLSX_HEADERS:
            raise ValueError(
                "Заголовки должны быть: Разрядность, Категория, ABC, Маска, Тип, Премиум, Покупка"
            )
        canonical = canonical_beauty_masks()
        out: list[MaskTypeImportRow] = []
        seen: set[tuple[str, str, str, str]] = set()
        for idx, raw in enumerate(rows_iter, start=2):
            cells = list(raw or ())
            while len(cells) < 7:
                cells.append(None)
            chunk = cells[:7]
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
                raise ValueError(f"Строка {idx}: повторяется комбинация разрядность/категория/ABC/маска")
            seen.add(key)
            out.append(
                MaskTypeImportRow(
                    digit_capacity=cap,
                    category=category,
                    abc=abc,
                    mask=mask,
                    type_label=_nullable_cell(chunk[4]),
                    premium=_nullable_cell(chunk[5]),
                    purchase=_nullable_cell(chunk[6]),
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
                        item.premium or "",
                        item.purchase or "",
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
                )
                self.db.add(row)
                by_key[key] = row
                inserted += 1
                continue
            row.type_label = item.type_label
            row.premium = item.premium
            row.purchase = item.purchase
            updated += 1
        self.db.commit()
        return MaskTypesLoadResult(
            ok=True,
            count=len(parsed),
            updated=updated,
            inserted=inserted,
            message=f"Обновлено: {updated}, добавлено: {inserted}",
        )
