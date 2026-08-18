from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.catalog.beauty_mask import enumerate_beauty_masks
from app.services.mask_types_service import (
    MASK_TYPES_XLSX_HEADERS,
    MASK_TYPES_XLSX_HEADERS_V7,
    MaskTypeImportRow,
    MaskTypesService,
    parse_mask_types_xlsx,
)
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook


def _xlsx_bytes(
    path: Path,
    rows: list[list[object]],
    headers: tuple[str, ...] = MASK_TYPES_XLSX_HEADERS,
) -> bytes:
    wb = open_styled_workbook(str(path), constant_memory=True)
    try:
        ws = wb.add_worksheet("Sheet1")
        writer = StyledSheetWriter(wb, ws, headers)
        for row in rows:
            writer.write_row(row)
        writer.finalize()
    finally:
        wb.close()
    return path.read_bytes()


def test_parse_numeric_excel_and_empty_abc(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "masks.xlsx",
        [[7.0, "Городской", "", "XXXXXXX", "Золотой", 100, 200.0, "1 500,5"]],
    )
    rows = parse_mask_types_xlsx(data)
    assert len(rows) == 1
    assert rows[0].digit_capacity == "7"
    assert rows[0].category == "Городской"
    assert rows[0].abc == ""
    assert rows[0].mask == "XXXXXXX"
    assert rows[0].type_label == "Золотой"
    assert rows[0].premium == Decimal("100")
    assert rows[0].purchase == Decimal("200")
    assert rows[0].period == Decimal("1500.5")


def test_parse_v7_headers_leave_period_null(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "masks_v7.xlsx",
        [[7.0, "Городской", "", "XXXXXXX", "Золотой", 100, 200]],
        headers=MASK_TYPES_XLSX_HEADERS_V7,
    )
    rows = parse_mask_types_xlsx(data)
    assert len(rows) == 1
    assert rows[0].premium == Decimal("100")
    assert rows[0].purchase == Decimal("200")
    assert rows[0].period is None


def test_parse_non_numeric_price_rejected(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "bad_price.xlsx",
        [[7, "Городской", "", "XXXXXXX", "Золотой", "премиум", "", ""]],
    )
    with pytest.raises(ValueError, match="некорректная цена"):
        parse_mask_types_xlsx(data)


def test_parse_unknown_mask_rejected(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "bad.xlsx",
        [[7, "Городской", "495", "OOOOOOO", "x", "", ""]],
    )
    with pytest.raises(ValueError, match="неизвестная маска"):
        parse_mask_types_xlsx(data)


def test_parse_duplicate_key_rejected(tmp_path: Path):
    mask = enumerate_beauty_masks(7)[0]
    data = _xlsx_bytes(
        tmp_path / "dup.xlsx",
        [
            [7, "Городской", "495", mask, "a", "", ""],
            [7, "Городской", "495", mask, "b", "", ""],
        ],
    )
    with pytest.raises(ValueError, match="повторяется"):
        parse_mask_types_xlsx(data)


def test_upsert_inserts_new_combo_without_deleting_seed(monkeypatch):
    seed = SimpleNamespace(
        id=uuid4(),
        digit_capacity="",
        category="",
        abc="",
        mask="XXXXXXX",
        type_label=None,
        premium=None,
        purchase=None,
        period=None,
    )
    db = MagicMock()
    db.scalar.return_value = 5220
    db.scalars.return_value.all.return_value = [seed]
    monkeypatch.setattr(
        "app.services.mask_types_service.parse_mask_types_xlsx",
        lambda _data: [
            MaskTypeImportRow(
                digit_capacity="7",
                category="Городской",
                abc="495",
                mask="XXXXXXX",
                type_label="москва",
                premium=Decimal("5"),
                purchase=Decimal("10"),
                period=Decimal("20"),
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.mask_types_service.ensure_mask_types_seeded",
        lambda _db: 0,
    )
    result = MaskTypesService(db).upsert_from_xlsx(b"unused")
    assert result.inserted == 1
    assert result.updated == 0
    assert seed.type_label is None
    db.add.assert_called_once()
    db.commit.assert_called()
