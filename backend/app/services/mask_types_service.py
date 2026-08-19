from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mask_types import MaskType
from app.modules.catalog.apply_mask_types import normalize_key_part
from app.modules.catalog.beauty_mask import (
    all_beauty_masks,
    canonical_beauty_masks,
    mask_digit_capacity,
)
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
_IMPORT_WIDTH = len(MASK_TYPES_XLSX_HEADERS)


@dataclass(frozen=True)
class MaskTypeImportRow:
    digit_capacity: str
    category: str
    abc: str
    mask: str
    type_label: str | None
    premium: Decimal | None
    purchase: Decimal | None


class _KeyedRow(Protocol):
    digit_capacity: str
    category: str
    abc: str
    mask: str


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


def is_mask_type_draft(row: _KeyedRow) -> bool:
    return (row.category or "") == "" and (row.abc or "") == ""


def key_absorbs(row: _KeyedRow, item: MaskTypeImportRow) -> bool:
    for existing, incoming in ((row.category or "", item.category), (row.abc or "", item.abc)):
        if existing and existing != incoming:
            return False
    return True


def filled_key_count(category: str, abc: str) -> int:
    return sum(1 for value in (category, abc) if value)


def row_key(row: _KeyedRow) -> tuple[str, str, str, str]:
    return (row.digit_capacity or "", row.category or "", row.abc or "", row.mask)


def apply_payload(row: MaskType, item: MaskTypeImportRow) -> None:
    row.type_label = item.type_label
    row.premium = item.premium
    row.purchase = item.purchase


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
        while len(header_cells) < _IMPORT_WIDTH:
            header_cells.append(None)
        got = tuple(_cell_text(c) for c in header_cells[:_IMPORT_WIDTH])
        if got != MASK_TYPES_XLSX_HEADERS:
            raise ValueError(
                "Заголовки должны быть: Разрядность, Категория, ABC, Маска, Тип, Премиум, Покупка"
            )
        canonical = canonical_beauty_masks()
        out: list[MaskTypeImportRow] = []
        seen: set[tuple[str, str, str, str]] = set()
        for idx, raw in enumerate(rows_iter, start=2):
            cells = list(raw or ())
            while len(cells) < _IMPORT_WIDTH:
                cells.append(None)
            chunk = cells[:_IMPORT_WIDTH]
            if _row_empty(chunk):
                continue
            category = _cell_text(chunk[1])
            abc = _cell_text(chunk[2])
            mask = _cell_text(chunk[3])
            if not mask:
                raise ValueError(f"Строка {idx}: не указана маска")
            if mask not in canonical:
                raise ValueError(f"Строка {idx}: неизвестная маска {mask}")
            cap = mask_digit_capacity(mask)
            key = (cap, category, abc, mask)
            if key in seen:
                raise ValueError(
                    f"Строка {idx}: повторяется комбинация разрядность/категория/ABC/маска"
                )
            seen.add(key)
            out.append(
                MaskTypeImportRow(
                    digit_capacity=cap,
                    category=category,
                    abc=abc,
                    mask=mask,
                    type_label=_nullable_cell(chunk[4]),
                    premium=_parse_price_cell(chunk[5], row=idx, column="Премиум"),
                    purchase=_parse_price_cell(chunk[6], row=idx, column="Покупка"),
                )
            )
        return out
    finally:
        wb.close()


def _backfill_digit_capacity(db: Session) -> None:
    rows = list(db.scalars(select(MaskType)).all())
    by_key = {row_key(row): row for row in rows}
    for row in rows:
        derived = mask_digit_capacity(row.mask)
        if (row.digit_capacity or "") == derived:
            continue
        target = (derived, row.category or "", row.abc or "", row.mask)
        occupied = by_key.get(target)
        if occupied is not None and occupied is not row:
            by_key.pop(row_key(row), None)
            db.delete(row)
            continue
        by_key.pop(row_key(row), None)
        row.digit_capacity = derived
        by_key[target] = row


def ensure_mask_types_seeded(db: Session) -> int:
    _backfill_digit_capacity(db)
    existing = set(db.scalars(select(MaskType.mask)).all())
    missing = [mask for mask in all_beauty_masks() if mask not in existing]
    if missing:
        db.add_all(
            [
                MaskType(
                    id=uuid4(),
                    digit_capacity=mask_digit_capacity(mask),
                    category="",
                    abc="",
                    mask=mask,
                )
                for mask in missing
            ]
        )
    db.commit()
    return len(missing)


def _pick_absorber(rows: list[MaskType], item: MaskTypeImportRow) -> MaskType | None:
    candidates = [row for row in rows if key_absorbs(row, item)]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: filled_key_count(row.category or "", row.abc or ""),
        reverse=True,
    )
    return candidates[0]


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
                        _xlsx_price(item.premium),
                        _xlsx_price(item.purchase),
                    ]
                )
            writer.finalize()
        finally:
            wb.close()
        return len(items)

    def upsert_from_xlsx(self, data: bytes) -> MaskTypesLoadResult:
        ensure_mask_types_seeded(self.db)
        parsed = parse_mask_types_xlsx(data)
        existing_rows = list(self.db.scalars(select(MaskType)).all())
        by_key = {row_key(row): row for row in existing_rows}
        by_mask: dict[str, list[MaskType]] = {}
        for row in existing_rows:
            by_mask.setdefault(row.mask, []).append(row)

        inserted = 0
        updated = 0
        deleted = 0

        def forget(row: MaskType) -> None:
            by_key.pop(row_key(row), None)
            bucket = by_mask.get(row.mask)
            if bucket:
                by_mask[row.mask] = [item for item in bucket if item is not row]

        def write_row(row: MaskType, item: MaskTypeImportRow) -> None:
            nonlocal deleted
            old = row_key(row)
            new = (item.digit_capacity, item.category, item.abc, item.mask)
            occupied = by_key.get(new)
            if occupied is not None and occupied is not row:
                forget(occupied)
                self.db.delete(occupied)
                deleted += 1
                self.db.flush()
            row.digit_capacity = item.digit_capacity
            row.category = item.category
            row.abc = item.abc
            apply_payload(row, item)
            if old != new:
                by_key.pop(old, None)
            by_key[new] = row
            self.db.flush()

        def add_row(item: MaskTypeImportRow) -> MaskType:
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
            self.db.flush()
            by_key[row_key(row)] = row
            by_mask.setdefault(row.mask, []).append(row)
            return row

        by_file: dict[str, list[MaskTypeImportRow]] = {}
        for item in parsed:
            by_file.setdefault(item.mask, []).append(item)

        for mask, file_items in by_file.items():
            db_rows = list(by_mask.get(mask, []))
            used_ids: set[object] = set()
            unique_pair = len(file_items) == 1 and len(db_rows) == 1

            for item in file_items:
                key = (item.digit_capacity, item.category, item.abc, item.mask)
                exact = by_key.get(key)
                if exact is not None and exact.mask == mask:
                    write_row(exact, item)
                    used_ids.add(exact.id)
                    updated += 1
                    continue

                if unique_pair:
                    write_row(db_rows[0], item)
                    used_ids.add(db_rows[0].id)
                    updated += 1
                    continue

                unused = [row for row in db_rows if row.id not in used_ids]
                absorber = _pick_absorber(unused, item)
                if absorber is not None:
                    write_row(absorber, item)
                    used_ids.add(absorber.id)
                    updated += 1
                    continue

                add_row(item)
                inserted += 1

            desired = {(it.category, it.abc) for it in file_items}
            for row in list(by_mask.get(mask, [])):
                if (row.category or "", row.abc or "") not in desired:
                    forget(row)
                    self.db.delete(row)
                    deleted += 1

            if not by_mask.get(mask):
                add_row(
                    MaskTypeImportRow(
                        digit_capacity=mask_digit_capacity(mask),
                        category="",
                        abc="",
                        mask=mask,
                        type_label=None,
                        premium=None,
                        purchase=None,
                    )
                )
                inserted += 1

        self.db.commit()
        return MaskTypesLoadResult(
            ok=True,
            count=len(parsed),
            updated=updated,
            inserted=inserted,
            message=(
                f"Обновлено: {updated}, добавлено: {inserted}, удалено: {deleted}"
            ),
        )
