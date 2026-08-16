"""Unit tests for Aurora Telecom CSV parser/mapper/multi-file (no live HTTP)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.enums import InventoryKind
from app.providers.aurora import contract, mapper, parser
from app.providers.aurora.client import AuroraClient
from app.providers.aurora.provider import AuroraProvider
from app.providers.dto.common import ConnectionConfig, RawHttpResult
from app.providers.errors import ProviderError, ProviderTransportError

SAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "providers"
    / "aurora"
    / "raw"
    / "sample.csv"
)


def _cfg(files: list[dict] | None = None) -> ConnectionConfig:
    entries = files if files is not None else [e.to_dict() for e in contract.seed_csv_files()]
    return ConnectionConfig(
        base_url=None,
        auth_settings={},
        extra_settings={"csv_files": entries},
    )


def _raw_from_bytes(data: bytes, status: int = 200, url: str = "") -> RawHttpResult:
    return RawHttpResult(
        status_code=status,
        body_text=data.decode("latin-1"),
        body_json={"bytes_len": len(data)},
        headers={},
        elapsed_ms=1.0,
        request_url=url
        or "http://bill.auroratelecom.ru:8080/bgbilling/numbers/Crimea.csv",
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


def test_status_column_flag_drops_sixth():
    text = (
        '"+7 (495) 2360003";СВОБОДЕН;ЗОЛОТОЙ;15990 Руб.;г. Москва;'
        "[ XXX-000-X - Первый десяток ]\n"
    )
    data = text.encode("cp1251")
    items, unmapped, meta = parser.parse_free_csv(
        _raw_from_bytes(data, url="http://bill.auroratelecom.ru:8080/bgbilling/numbers/other.csv"),
        raw_bytes=data,
        filename="other.csv",
        has_status_column=True,
    )
    assert meta["unmapped"] == 0
    assert len(items) == 1
    assert unmapped == []
    item = items[0]
    assert item.msisdn == "74952360003"
    assert item.number_type == "ЗОЛОТОЙ"
    assert item.period_price == Decimal("15990")
    assert item.city_name == "г. Москва"
    assert item.raw_payload.get("dropped_status_column") is True
    assert item.raw_payload.get("column_count") == 6


def test_six_column_unmapped_without_flag():
    text = (
        '"+7 (495) 2360003";СВОБОДЕН;ЗОЛОТОЙ;15990 Руб.;г. Москва;'
        "[ XXX-000-X - Первый десяток ]\n"
    )
    data = text.encode("cp1251")
    items, unmapped, meta = parser.parse_free_csv(
        _raw_from_bytes(
            data, url="http://bill.auroratelecom.ru:8080/bgbilling/numbers/MSK.csv"
        ),
        raw_bytes=data,
        filename="MSK.csv",
        has_status_column=False,
    )
    assert items == []
    assert len(unmapped) == 1
    assert meta["unmapped"] == 1
    assert unmapped[0].get("column_count") == 6


def test_load_csv_files_from_settings():
    entries = contract.load_csv_files(
        {
            "csv_files": [
                {
                    "url": "http://bill.auroratelecom.ru:8080/bgbilling/numbers/Crimea.csv",
                    "has_status_column": False,
                },
                {
                    "url": "http://bill.auroratelecom.ru:8080/bgbilling/numbers/MSK.csv",
                    "has_status_column": True,
                },
            ]
        }
    )
    assert len(entries) == 2
    assert entries[1].has_status_column is True


def test_load_csv_files_empty_raises():
    with pytest.raises(ProviderError, match="empty"):
        contract.load_csv_files({"csv_files": []})


def test_reject_all_free_url():
    with pytest.raises(ProviderError, match="all_free"):
        contract.validate_csv_url(
            "http://bill.auroratelecom.ru:8080/bgbilling/numbers/all_free.csv"
        )


def test_legacy_backfill_flags_msk():
    entries = contract.legacy_backfill_entries(
        "http://bill.auroratelecom.ru:8080/bgbilling/numbers/all_free.csv"
    )
    assert len(entries) == 6
    assert "all_free.csv" not in "".join(e.url for e in entries)
    msk = next(e for e in entries if e.url.endswith("/MSK.csv"))
    assert msk.has_status_column is True
    assert entries[0].url.endswith("/Crimea.csv")


def test_client_requires_csv_files():
    with pytest.raises(ProviderError, match="empty"):
        AuroraClient(ConnectionConfig(base_url=None, auth_settings={}, extra_settings={}))


def test_client_loads_configured_files():
    client = AuroraClient(_cfg())
    assert len(client.csv_urls) == 6
    assert client.csv_url.endswith("/Crimea.csv")
    assert client.first_entry.has_status_column is False
    msk = next(e for e in client.csv_files if e.url.endswith("/MSK.csv"))
    assert msk.has_status_column is True


def test_decode_prefers_valid_utf8_over_cp1251_mojibake():
    line = (
        '"+7 (495) 2360003";ПРОСТОЙ;990 Руб.;г. Москва;'
        "[ AAA-XXX - test ]\n"
    )
    data = line.encode("utf-8")
    text, enc = parser.decode_csv_bytes(data)
    assert enc == "utf-8-sig"
    assert "ПРОСТОЙ" in text
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
    head = SAMPLE_PATH.read_bytes()[:800]
    cut = head.rstrip(b"\r\n")
    assert not cut.endswith((b"\n", b"\r"))
    sample, meta = parser.parse_probe_bytes(cut, truncated=True)
    assert sample is not None
    assert sample.msisdn and sample.msisdn.startswith("7")
    assert meta.get("scanned_rows", 0) >= 1


def test_sync_keeps_cross_file_duplicates_for_engine(monkeypatch):
    """Provider returns all mapped rows; persist/XLSX dedupe (last wins) happens later."""
    row_a = (
        '"+7 (495) 1111111";ПРОСТОЙ;100 Руб.;г. Москва;[x]\n'
        '"+7 (495) 2222222";ПРОСТОЙ;100 Руб.;г. Москва;[x]\n'
    ).encode("cp1251")
    row_b = (
        '"+7 (495) 2222222";ПРОСТОЙ;200 Руб.;г. Москва;[dup]\n'
        '"+7 (812) 3333333";ПРОСТОЙ;100 Руб.;г. Санкт-Петербург;[x]\n'
    ).encode("cp1251")

    async def fake_fetch(self, url: str | None = None) -> RawHttpResult:
        target = url or self.csv_url
        name = target.rsplit("/", 1)[-1]
        if name == "Crimea.csv":
            data = row_a
        elif name == "Grozny.csv":
            data = row_b
        else:
            data = b"\n"  # empty regional export (no rows)
        return _raw_from_bytes(data, url=target)

    monkeypatch.setattr(AuroraClient, "fetch_csv", fake_fetch)

    progress: list[str] = []

    def on_progress(detail: str, current=None, total=None):
        progress.append(detail)

    result = asyncio.run(
        AuroraProvider().sync_free_numbers(
            _cfg(),
            on_progress=on_progress,
        )
    )
    keys = [n.provider_number_key for n in result.items]
    assert sorted(keys) == [
        "74951111111",
        "74952222222",
        "74952222222",
        "78123333333",
    ]
    assert result.parsed == 4
    assert "duplicates_skipped=" not in " ".join(result.warnings)
    assert any("Crimea.csv" in d for d in progress)
    assert any("итого" in d and "4 номеров" for d in progress)

    from app.modules.sync_engine.dropped_export import split_dedupe_drops

    dropped, kept = split_dedupe_drops(result.items)
    assert len(kept) == 3
    assert len(dropped) == 1
    assert dropped[0].provider_number_key == "74952222222"
    # last-wins keeps the later file's fee
    kept_dup = next(n for n in kept if n.provider_number_key == "74952222222")
    assert kept_dup.period_price == Decimal("200")


def test_sync_fail_closed_on_one_file(monkeypatch):
    calls: list[str] = []

    async def fake_fetch(self, url: str | None = None) -> RawHttpResult:
        target = url or self.csv_url
        name = target.rsplit("/", 1)[-1]
        calls.append(name)
        if name == "Grozny.csv":
            raise ProviderTransportError(
                "Aurora CSV HTTP 500 for Grozny.csv",
                details={"file": "Grozny.csv"},
            )
        data = '"+7 (495) 1111111";ПРОСТОЙ;100 Руб.;г. Москва;[x]\n'.encode("cp1251")
        return _raw_from_bytes(data, url=target)

    monkeypatch.setattr(AuroraClient, "fetch_csv", fake_fetch)

    with pytest.raises(ProviderTransportError, match="Grozny"):
        asyncio.run(AuroraProvider().sync_free_numbers(_cfg()))
    assert "Crimea.csv" in calls
    assert "Grozny.csv" in calls
    # Fail-closed: must not continue past the failed file
    assert "MSK.csv" not in calls
