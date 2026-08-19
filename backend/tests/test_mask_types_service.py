from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.catalog.beauty_mask import enumerate_beauty_masks, mask_digit_capacity
from app.modules.catalog.number_category import (
    CATEGORY_GEOGRAPHIC,
    CATEGORY_MOBILE,
    CATEGORY_TOLLFREE,
)
from app.services.mask_types_service import (
    MASK_TYPES_XLSX_HEADERS,
    MaskTypeImportRow,
    MaskTypesService,
    ensure_mask_types_seeded,
    parse_mask_types_xlsx,
    _backfill_digit_capacity,
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


def _required_seven(mask: str = "XXXXXXX") -> list[SimpleNamespace]:
    return [
        _row(mask=mask, digit_capacity="7", category=CATEGORY_GEOGRAPHIC),
        _row(mask=mask, digit_capacity="7", category=CATEGORY_MOBILE),
        _row(mask=mask, digit_capacity="7", category=CATEGORY_TOLLFREE),
    ]


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


def test_parse_five_digit_forces_geographic(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "five.xlsx",
        [[5, "Мобильный", "", "00000", "x", 1, 2]],
    )
    rows = parse_mask_types_xlsx(data)
    assert rows[0].digit_capacity == "5"
    assert rows[0].category == CATEGORY_GEOGRAPHIC
    assert rows[0].mask == "00000"


def test_parse_five_digit_duplicate_after_force(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "five_dup.xlsx",
        [
            [5, "Городской", "", "00000", "a", 1, 2],
            [5, "Мобильный", "", "00000", "b", 1, 2],
        ],
    )
    with pytest.raises(ValueError, match="повторяется"):
        parse_mask_types_xlsx(data)


def test_parse_seven_empty_category_becomes_geographic(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "empty_cat.xlsx",
        [[7, "", "", "XXXXXXX", "Золотой", 100, 200]],
    )
    rows = parse_mask_types_xlsx(data)
    assert rows[0].category == CATEGORY_GEOGRAPHIC


def test_parse_seven_unknown_category_rejected(tmp_path: Path):
    data = _xlsx_bytes(
        tmp_path / "bad_cat.xlsx",
        [[7, "Бесплатный доступ", "", "XXXXXXX", "x", "", ""]],
    )
    with pytest.raises(ValueError, match="неизвестная категория"):
        parse_mask_types_xlsx(data)


def test_ensure_coerces_empty_and_adds_required(monkeypatch):
    seed = _row(digit_capacity="7", category="", abc="", mask="XXXXXXX")
    five = _row(
        digit_capacity="5",
        category=CATEGORY_MOBILE,
        abc="",
        mask="00000",
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [seed, five]
    monkeypatch.setattr(
        "app.services.mask_types_service.all_beauty_masks",
        lambda: ("XXXXXXX", "00000"),
    )
    added = ensure_mask_types_seeded(db)
    assert seed.category == CATEGORY_GEOGRAPHIC
    assert five.category == CATEGORY_GEOGRAPHIC
    cats = {(row.mask, row.category) for row in db.add_all.call_args[0][0]}
    assert ("XXXXXXX", CATEGORY_MOBILE) in cats
    assert ("XXXXXXX", CATEGORY_TOLLFREE) in cats
    assert ("00000", CATEGORY_GEOGRAPHIC) not in cats
    assert added == 2


def test_backfill_digit_capacity_merges_payload_on_collision():
    keep = _row(
        digit_capacity="7",
        category=CATEGORY_GEOGRAPHIC,
        abc="",
        mask="XXXXXXX",
        type_label=None,
        premium=None,
        purchase=Decimal("8"),
    )
    drop = _row(
        digit_capacity="",
        category=CATEGORY_GEOGRAPHIC,
        abc="",
        mask="XXXXXXX",
        type_label="Золотой",
        premium=Decimal("9"),
        purchase=Decimal("1"),
    )
    db = MagicMock()
    by_key = {
        ("7", CATEGORY_GEOGRAPHIC, "", "XXXXXXX"): keep,
        ("", CATEGORY_GEOGRAPHIC, "", "XXXXXXX"): drop,
    }
    _backfill_digit_capacity(db, by_key)
    assert keep.type_label == "Золотой"
    assert keep.premium == Decimal("9")
    assert keep.purchase == Decimal("8")
    db.delete.assert_called_once_with(drop)
    assert ("", CATEGORY_GEOGRAPHIC, "", "XXXXXXX") not in by_key


def test_upsert_abc_override_keeps_required(monkeypatch):
    geo, mobile, toll = _required_seven()
    service, db = _service([geo, mobile, toll], monkeypatch, [_item(abc="495")])
    result = service.upsert_from_xlsx(b"unused")
    assert result.inserted == 1
    assert result.updated == 0
    assert geo.abc == ""
    assert geo.category == CATEGORY_GEOGRAPHIC
    db.add.assert_called_once()
    db.delete.assert_not_called()


def test_upsert_updates_mobile_without_touching_geographic(monkeypatch):
    geo, mobile, toll = _required_seven()
    geo.type_label = "город"
    service, db = _service(
        [geo, mobile, toll],
        monkeypatch,
        [_item(category=CATEGORY_MOBILE, abc="", type_label="моб")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert result.inserted == 0
    assert mobile.type_label == "моб"
    assert geo.type_label == "город"
    db.add.assert_not_called()
    db.delete.assert_not_called()


def test_upsert_file_with_both_categories_updates_and_inserts_abc(monkeypatch):
    geo, mobile, toll = _required_seven()
    extra = _row(category=CATEGORY_GEOGRAPHIC, abc="495", type_label="москва")
    service, db = _service(
        [geo, mobile, toll, extra],
        monkeypatch,
        [
            _item(category=CATEGORY_GEOGRAPHIC, abc="495", type_label="москва"),
            _item(category=CATEGORY_MOBILE, abc="", type_label="моб"),
        ],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 2
    assert result.inserted == 0
    assert extra.type_label == "москва"
    assert mobile.type_label == "моб"
    db.delete.assert_not_called()


def test_upsert_empty_payload_overwrites(monkeypatch):
    geo, mobile, toll = _required_seven()
    geo.type_label = "Золотой"
    geo.premium = Decimal("9")
    geo.purchase = Decimal("8")
    service, _db = _service(
        [geo, mobile, toll],
        monkeypatch,
        [_item(category=CATEGORY_GEOGRAPHIC, abc="", type_label=None, premium=None, purchase=None)],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert geo.type_label is None
    assert geo.premium is None
    assert geo.purchase is None
    assert geo.category == CATEGORY_GEOGRAPHIC


def test_upsert_keeps_required_mobile_when_missing_from_file(monkeypatch):
    geo, mobile, toll = _required_seven()
    extra = _row(category=CATEGORY_MOBILE, abc="903", type_label="extra")
    service, db = _service(
        [geo, mobile, toll, extra],
        monkeypatch,
        [_item(category=CATEGORY_GEOGRAPHIC, abc="")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert result.inserted == 0
    assert mobile.category == CATEGORY_MOBILE
    db.delete.assert_called()
    assert db.delete.call_args[0][0] is extra


def test_upsert_leaves_masks_not_in_file(monkeypatch):
    other_mask = enumerate_beauty_masks(6)[0]
    keep = _row(
        mask=other_mask,
        digit_capacity=mask_digit_capacity(other_mask),
        category=CATEGORY_GEOGRAPHIC,
        abc="495",
        type_label="keep",
    )
    geo, mobile, toll = _required_seven()
    service, db = _service(
        [keep, geo, mobile, toll],
        monkeypatch,
        [_item(category=CATEGORY_GEOGRAPHIC, abc="")],
    )
    result = service.upsert_from_xlsx(b"unused")
    assert result.updated == 1
    assert result.inserted == 0
    assert keep.category == CATEGORY_GEOGRAPHIC
    assert keep.type_label == "keep"
    db.delete.assert_not_called()
    db.add.assert_not_called()


def test_parse_filters_json_and_empty():
    assert MaskTypesService.parse_filters(None) == {}
    assert MaskTypesService.parse_filters("") == {}
    assert MaskTypesService.parse_filters('{"category":["Мобильный"]}') == {
        "category": ["Мобильный"]
    }
    with pytest.raises(ValueError, match="JSON object"):
        MaskTypesService.parse_filters("[1]")


def test_list_items_does_not_seed(monkeypatch):
    called: list[int] = []
    monkeypatch.setattr(
        "app.services.mask_types_service.ensure_mask_types_seeded",
        lambda _db: called.append(1) or 0,
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    MaskTypesService(db).list_items()
    assert called == []


def test_list_page_total_and_size():
    rows = [_row(mask="AAAAAAA"), _row(mask="BBBBBBB")]
    db = MagicMock()
    db.scalar.return_value = 13500
    db.scalars.return_value.all.return_value = rows
    page = MaskTypesService(db).list_page(page=1, page_size=100)
    assert page.total == 13500
    assert page.page_size == 100
    assert page.total_pages == 135
    assert [item.mask for item in page.items] == ["AAAAAAA", "BBBBBBB"]


def test_filtered_stmt_mask_q_category_and_empty_abc():
    stmt = MaskTypesService(MagicMock())._filtered_stmt(
        mask_q="123",
        filters={"abc": ["__empty__"], "category": ["Мобильный"]},
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "like" in sql
    assert "%123%" in sql
    assert "мобильный" in sql
    assert "is null" in sql


def test_filtered_stmt_excludes_facet_column():
    svc = MaskTypesService(MagicMock())
    full = str(
        svc._filtered_stmt(
            filters={"category": ["Мобильный"], "abc": ["495"]}
        ).compile(compile_kwargs={"literal_binds": True})
    )
    excluded = str(
        svc._filtered_stmt(
            filters={"category": ["Мобильный"], "abc": ["495"]},
            exclude_column="category",
        ).compile(compile_kwargs={"literal_binds": True})
    )
    assert "Мобильный" in full
    assert "Мобильный" not in excluded
    assert "495" in excluded


def test_filtered_stmt_rounds_price_token():
    sql = str(
        MaskTypesService(MagicMock())
        ._filtered_stmt(filters={"premium": ["2 222"]})
        .compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "round" in sql
    assert "2222" in sql.replace(" ", "")


def test_list_facets_unsupported_column():
    with pytest.raises(ValueError, match="Unsupported"):
        MaskTypesService(MagicMock()).list_facets(column="nope")


def test_list_facets_empty_token_and_truncated():
    db = MagicMock()
    db.execute.return_value.all.return_value = [(None, 5), ("Мобильный", 3), ("x", 1)]
    result = MaskTypesService(db).list_facets(column="category", limit=2)
    assert result.truncated is True
    assert result.items[0].value == ""
    assert result.items[0].count == 5
    assert result.items[1].value == "Мобильный"


def test_list_facets_formats_price():
    db = MagicMock()
    db.execute.return_value.all.return_value = [(2222, 2)]
    result = MaskTypesService(db).list_facets(column="premium")
    assert result.items[0].value == "2 222"

