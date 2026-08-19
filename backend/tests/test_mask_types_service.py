from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.catalog.beauty_mask import enumerate_beauty_masks, mask_digit_capacity
from app.services.mask_types_service import (
    MASK_TYPES_XLSX_HEADERS,
    MaskTypeImportRow,
    MaskTypesService,
    filled_key_count,
    is_mask_type_draft,
    key_absorbs,
    parse_mask_types_xlsx,
    row_key,
)
from app.services.xlsx_style import StyledSheetWriter, open_styled_workbook

_HEADERS_V8 = (*MASK_TYPES_XLSX_HEADERS, "Абонплата")


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


def _row(**kwargs: object) -> SimpleNamespace:
    data = {
        "id": uuid4(),
        "digit_capacity": "7",
        "category": "",
        "abc": "",
        "mask": "XXXXXXX",
        "type_label": None,
        "premium": None,
        "purchase": None,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _item(**kwargs: object) -> MaskTypeImportRow:
    data = {
        "digit_capacity": "7",
        "category": "Городской",
        "abc": "",
        "mask": "XXXXXXX",
        "type_label": "Золотой",
        "premium": Decimal("100"),
        "purchase": Decimal("200"),
    }
    data.update(kwargs)
    return MaskTypeImportRow(**data)  # type: ignore[arg-type]


def _service(rows: list[SimpleNamespace], monkeypatch: pytest.MonkeyPatch, parsed: list[MaskTypeImportRow]):
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    monkeypatch.setattr(
        "app.services.mask_types_service.parse_mask_types_xlsx",
        lambda _data: parsed,
    )
    monkeypatch.setattr(
        "app.services.mask_types_service.ensure_mask_types_seeded",
        lambda _db: 0,
    )
    return MaskTypesService(db), db


def test_parse_numeric_excel_and_empty_abc(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "masks.xlsx",
        [[7.0, "Городской", "", "XXXXXXX", "Золотой", 100, 200.0]],
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
    assert not hasattr(rows[0], "period")


def test_parse_ignores_xlsx_capacity_column(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "cap.xlsx",
        [
            ["", "Городской", "", "XXXXXXX", "Золотой", 1, 2],
            [5, "Городской", "", "XXXXXXX", "x", 1, 2],
        ],
    )
    with pytest.raises(ValueError, match="повторяется"):
        parse_mask_types_xlsx(data)


def test_parse_empty_capacity_uses_mask_length(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "empty_cap.xlsx",
        [["", "Городской", "", "XXXXXXX", "Золотой", 100, 200]],
    )
    rows = parse_mask_types_xlsx(data)
    assert rows[0].digit_capacity == mask_digit_capacity("XXXXXXX")
    assert rows[0].category == "Городской"


def test_parse_extra_eighth_column_ignored(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "masks_v8.xlsx",
        [[7.0, "Городской", "", "XXXXXXX", "Золотой", 100, 200, "премиум"]],
        headers=_HEADERS_V8,
    )
    rows = parse_mask_types_xlsx(data)
    assert len(rows) == 1
    assert rows[0].premium == Decimal("100")
    assert rows[0].purchase == Decimal("200")


def test_parse_empty_type_and_prices(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "empty_payload.xlsx",
        [[7, "Городской", "", "XXXXXXX", "", "", ""]],
    )
    rows = parse_mask_types_xlsx(data)
    assert rows[0].type_label is None
    assert rows[0].premium is None
    assert rows[0].purchase is None


def test_parse_non_numeric_price_rejected(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "bad_price.xlsx",
        [[7, "Городской", "", "XXXXXXX", "Золотой", "премиум", ""]],
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


def test_key_absorbs_draft_and_rejects_other_category():
    draft = _row(digit_capacity="7", category="", abc="")
    filled = _row(digit_capacity="7", category="Городской", abc="")
    item_city = _item(category="Городской", abc="495")
    item_mobile = _item(category="Мобильный", abc="")
    assert key_absorbs(draft, item_city)
    assert key_absorbs(filled, item_city)
    assert not key_absorbs(filled, item_mobile)
    assert filled_key_count("", "495") == 1
    assert is_mask_type_draft(draft)
    assert not is_mask_type_draft(filled)


def test_upsert_fills_seed_category_in_place(monkeypatch):
    seed = _row(digit_capacity="7", category="", abc="", type_label=None)
    service, db = _service([seed], monkeypatch, [_item(abc="495")])
    result = service.upsert_from_xlsx(b"unused")
    assert result.inserted == 0
    assert result.updated == 1
    assert seed.category == "Городской"
    assert seed.abc == "495"
    assert seed.type_label == "Золотой"
    assert seed.premium == Decimal("100")
    db.add.assert_not_called()


def test_upsert_single_file_row_replaces_unique_mask(monkeypatch):
    existing = _row(category="Городской", abc="495", type_label="москва")
    service, db = _service(
        [existing],
        monkeypatch,
        [_item(category="Мобильный", abc="", type_label="моб")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.inserted == 0
    assert result.updated == 1
    assert existing.category == "Мобильный"
    assert existing.abc == ""
    assert existing.type_label == "моб"
    db.add.assert_not_called()


def test_upsert_adds_second_category_when_both_in_file(monkeypatch):
    existing = _row(category="Городской", abc="495", type_label="москва")
    service, db = _service(
        [existing],
        monkeypatch,
        [
            _item(category="Городской", abc="495", type_label="москва"),
            _item(category="Мобильный", abc="", type_label="моб"),
        ],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.inserted == 1
    assert result.updated == 1
    assert existing.category == "Городской"
    db.add.assert_called_once()


def test_upsert_empty_payload_overwrites(monkeypatch):
    existing = _row(
        category="Городской",
        abc="",
        type_label="Золотой",
        premium=Decimal("9"),
        purchase=Decimal("8"),
    )
    service, _db = _service(
        [existing],
        monkeypatch,
        [_item(category="Городской", abc="", type_label=None, premium=None, purchase=None)],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert existing.type_label is None
    assert existing.premium is None
    assert existing.purchase is None


def test_upsert_prefers_most_specific_absorber(monkeypatch):
    draft = _row(category="", abc="")
    partial = _row(category="", abc="495")
    service, db = _service(
        [draft, partial],
        monkeypatch,
        [_item(category="Городской", abc="495")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert result.inserted == 0
    assert partial.category == "Городской"
    db.add.assert_not_called()
    db.delete.assert_called()
    assert db.delete.call_args[0][0] is draft


def test_upsert_empty_category_overwrites_unique_mask(monkeypatch):
    concrete = _row(category="Городской", abc="", type_label="Золотой")
    service, db = _service(
        [concrete],
        monkeypatch,
        [_item(category="", abc="", type_label=None, premium=None, purchase=None)],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.inserted == 0
    assert result.updated == 1
    assert concrete.category == ""
    assert concrete.type_label is None
    assert concrete.premium is None
    db.add.assert_not_called()


def test_upsert_collision_writes_existing_key(monkeypatch):
    draft = _row(category="", abc="")
    existing = _row(category="Городской", abc="495", type_label="old")
    service, db = _service(
        [draft, existing],
        monkeypatch,
        [_item(category="Городской", abc="495", type_label="new")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert existing.type_label == "new"
    assert draft.category == ""
    db.add.assert_not_called()
    db.delete.assert_called()
    assert db.delete.call_args[0][0] is draft
    assert row_key(existing)[1] == "Городской"


def test_upsert_deletes_combo_missing_from_file(monkeypatch):
    city = _row(category="Городской", abc="")
    mobile = _row(category="Мобильный", abc="")
    service, db = _service(
        [city, mobile],
        monkeypatch,
        [_item(category="Городской", abc="")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert result.inserted == 0
    assert city.category == "Городской"
    db.delete.assert_called()
    assert db.delete.call_args[0][0] is mobile


def test_upsert_leaves_masks_not_in_file(monkeypatch):
    other_mask = enumerate_beauty_masks(6)[0]
    keep = _row(
        mask=other_mask,
        digit_capacity=mask_digit_capacity(other_mask),
        category="Городской",
        abc="495",
        type_label="keep",
    )
    city = _row(category="Городской", abc="")
    service, db = _service(
        [keep, city],
        monkeypatch,
        [_item(category="Городской", abc="")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert result.inserted == 0
    assert keep.category == "Городской"
    assert keep.type_label == "keep"
    db.delete.assert_not_called()
    db.add.assert_not_called()


def test_upsert_empty_file_row_replaces_categories_with_draft(monkeypatch):
    city = _row(category="Городской", abc="", type_label="a")
    mobile = _row(category="Мобильный", abc="", type_label="b")
    service, db = _service(
        [city, mobile],
        monkeypatch,
        [_item(category="", abc="", type_label=None, premium=None, purchase=None)],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.inserted == 1
    assert result.updated == 0
    db.add.assert_called_once()
    assert db.delete.call_count == 2
