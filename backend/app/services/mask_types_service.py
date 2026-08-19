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
from app.modules.catalog.mask_type_policy import (
    is_required_key,
    mask_row_fill_color,
    normalize_import_category,
    required_categories,
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
            try:
                category = normalize_import_category(cap, category)
            except ValueError as exc:
                raise ValueError(f"Строка {idx}: {exc}") from exc
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


def _merge_payload(keep: MaskType, drop: MaskType) -> None:
    if not (keep.type_label or "") and (drop.type_label or ""):
        keep.type_label = drop.type_label
    if keep.premium is None and drop.premium is not None:
        keep.premium = drop.premium
    if keep.purchase is None and drop.purchase is not None:
        keep.purchase = drop.purchase


def _backfill_digit_capacity(db: Session, by_key: dict[tuple[str, str, str, str], MaskType]) -> None:
    for row in list(by_key.values()):
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


def _coerce_directory_categories(
    db: Session, by_key: dict[tuple[str, str, str, str], MaskType]
) -> None:
    for row in list(by_key.values()):
        cap = mask_digit_capacity(row.mask)
        current = row.category or ""
        if cap in {"5", "6"} or current == "":
            target_cat = normalize_import_category(cap, current)
        else:
            continue
        if current == target_cat and (row.digit_capacity or "") == cap:
            continue
        target = (cap, target_cat, row.abc or "", row.mask)
        occupied = by_key.get(target)
        old = row_key(row)
        if occupied is not None and occupied is not row:
            _merge_payload(occupied, row)
            by_key.pop(old, None)
            db.delete(row)
            continue
        by_key.pop(old, None)
        row.digit_capacity = cap
        row.category = target_cat
        by_key[target] = row


def ensure_mask_types_seeded(db: Session) -> int:
    rows = list(db.scalars(select(MaskType)).all())
    by_key = {row_key(row): row for row in rows}
    _backfill_digit_capacity(db, by_key)
    _coerce_directory_categories(db, by_key)
    db.flush()
    to_add: list[MaskType] = []
    for mask in all_beauty_masks():
        cap = mask_digit_capacity(mask)
        for category in required_categories(cap):
            key = (cap, category, "", mask)
            if key in by_key:
                continue
            row = MaskType(
                id=uuid4(),
                digit_capacity=cap,
                category=category,
                abc="",
                mask=mask,
            )
            to_add.append(row)
            by_key[key] = row
    if to_add:
        db.add_all(to_add)
    db.commit()
    return len(to_add)


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
                    ],
                    fill_color=mask_row_fill_color(item.category, item.premium),
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
            for item in file_items:
                key = (item.digit_capacity, item.category, item.abc, item.mask)
                exact = by_key.get(key)
                if exact is not None:
                    apply_payload(exact, item)
                    updated += 1
                    continue
                add_row(item)
                inserted += 1

            desired = {(it.category, it.abc) for it in file_items}
            cap = mask_digit_capacity(mask)
            for row in list(by_mask.get(mask, [])):
                combo = (row.category or "", row.abc or "")
                if combo in desired:
                    continue
                if is_required_key(
                    digit_capacity=row.digit_capacity or cap,
                    category=row.category or "",
                    abc=row.abc or "",
                ):
                    continue
                forget(row)
                self.db.delete(row)
                deleted += 1

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
