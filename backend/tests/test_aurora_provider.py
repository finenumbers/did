"""Unit tests for Aurora Telecom CSV parser/mapper (no live HTTP)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.models.enums import InventoryKind
from app.providers.aurora import mapper, parser
from app.providers.dto.common import RawHttpResult

SAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "providers"
    / "aurora"
    / "raw"
    / "sample.csv"
)


def _raw_from_bytes(data: bytes, status: int = 200) -> RawHttpResult:
    return RawHttpResult(
        status_code=status,
        body_text=data.decode("latin-1"),
        body_json={"bytes_len": len(data)},
        headers={},
        elapsed_ms=1.0,
        request_url="http://bill.auroratelecom.ru:8080/bgbilling/numbers/all_free.csv",
    )


def test_normalize_phone():
    assert parser.normalize_phone("+7 (3652) 777007") == "73652777007"
    assert parser.normalize_phone("+7 (495) 2360003") == "74952360003"
    assert parser.normalize_phone("89001234567") == "79001234567"
    assert parser.normalize_phone("9001234567") == "79001234567"
    assert parser.normalize_phone(None) is None
    assert parser.normalize_phone("12345") is None
    assert parser.normalize_phone("749512") is None


def test_parse_period_price():
    assert parser.parse_period_price("75990 Руб.") == Decimal("75990")
    assert parser.parse_period_price("990 Руб.") == Decimal("990")
    assert parser.parse_period_price("ДОГОВОРНАЯ") is None
    assert parser.parse_period_price("") is None


def test_parse_region_pipe():
    assert parser.parse_region("г. Симферополь|Республика Крым") == (
        "г. Симферополь",
        "Республика Крым",
    )


def test_parse_region_city_only():
    assert parser.parse_region("г. Москва") == ("г. Москва", None)
    assert parser.parse_region("г. Санкт-Петербург") == ("г. Санкт-Петербург", None)


def test_parse_region_region_only():
    assert parser.parse_region("Российская Федерация") == (None, "Российская Федерация")


def test_parse_row_and_map():
    row = [
        "+7 (3652) 777007",
        "ПЛАТИНОВЫЙ",
        "75990 Руб.",
        "г. Симферополь|Республика Крым",
        "[ AAA-XXX - 3 одинаковых в начале ]",
    ]
    parsed = parser.parse_row(row)
    assert parsed is not None
    assert parsed.msisdn == "73652777007"
    assert parsed.number_type == "ПЛАТИНОВЫЙ"
    assert parsed.period_price == Decimal("75990")
    assert parsed.city_name == "г. Симферополь"
    assert parsed.region_name == "Республика Крым"
    assert parsed.display_mask and "AAA-XXX" in parsed.display_mask

    mapped = mapper.map_number(parsed)
    assert mapped is not None
    assert mapped.inventory_kind == InventoryKind.free
    assert mapped.provider_number_key == "73652777007"
    assert mapped.period_price == Decimal("75990")
    assert mapped.number_type == "ПЛАТИНОВЫЙ"
    assert mapped.display_mask == parsed.display_mask
    assert mapped.abc_code is not None


def test_parse_sample_fixture():
    data = SAMPLE_PATH.read_bytes()
    items, unmapped, meta = parser.parse_free_csv(_raw_from_bytes(data), raw_bytes=data)
    assert meta["encoding"] == "cp1251"
    assert meta["row_count"] >= 5
    assert len(items) == meta["parsed"]
    assert len(items) + len(unmapped) == meta["row_count"]
    assert all(i.msisdn and i.msisdn.startswith("7") for i in items)


def test_short_row_unmapped():
    text = '"+7 (495) 2360003";ПРОСТОЙ\n'
    data = text.encode("cp1251")
    items, unmapped, meta = parser.parse_free_csv(_raw_from_bytes(data), raw_bytes=data)
    assert items == []
    assert len(unmapped) == 1
    assert meta["unmapped"] == 1


def test_whitespace_base_url_falls_back_to_default():
    from app.providers.aurora.client import AuroraClient
    from app.providers.aurora import contract
    from app.providers.dto.common import ConnectionConfig

    client = AuroraClient(ConnectionConfig(base_url="   ", auth_settings={}))
    assert client.csv_url == contract.DEFAULT_CSV_URL


def test_decode_prefers_valid_utf8_over_cp1251_mojibake():
    line = (
        '"+7 (495) 2360003";ПРОСТОЙ;990 Руб.;г. Москва;'
        "[ AAA-XXX - test ]\n"
    )
    data = line.encode("utf-8")
    text, enc = parser.decode_csv_bytes(data)
    assert enc == "utf-8-sig"
    assert "ПРОСТОЙ" in text
    # Live-like cp1251 still selects primary encoding
    cp = line.encode("cp1251")
    _text2, enc2 = parser.decode_csv_bytes(cp)
    assert enc2 == "cp1251"


def test_parse_probe_bytes_first_row():
    data = SAMPLE_PATH.read_bytes()[:4096]
    sample, meta = parser.parse_probe_bytes(data)
    assert sample is not None
    assert sample.msisdn and sample.msisdn.startswith("7")
    assert meta.get("encoding") == "cp1251"


def test_parse_probe_discards_truncated_trailing_line():
    """Stream head may cut mid-row; truncated trailing line must not break parse."""
    head = SAMPLE_PATH.read_bytes()[:800]
    # Ensure we cut mid-line (no trailing newline) and mark truncated
    cut = head.rstrip(b"\r\n")
    assert not cut.endswith((b"\n", b"\r"))
    sample, meta = parser.parse_probe_bytes(cut, truncated=True)
    assert sample is not None
    assert sample.msisdn and sample.msisdn.startswith("7")
    assert meta.get("scanned_rows", 0) >= 1
