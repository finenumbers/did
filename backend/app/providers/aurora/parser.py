"""Parse Aurora free CSV. Docs: aurora-contract.md / aurora-field-mapping.md."""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.providers.aurora import contract
from app.providers.dto.common import RawHttpResult
from app.providers.dto.numbers import ParsedNumberItem
from app.providers.errors import ProviderParseError
from app.providers.msisdn_split import normalize_phone

_FEE_NUMBER_RE = re.compile(r"(\d[\d\s\u00a0]*)")


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def parse_period_price(value: Any) -> Decimal | None:
    """Extract Decimal from texts like '75990 Руб.'; ДОГОВОРНАЯ → None."""
    text = _as_text(value)
    if not text:
        return None
    m = _FEE_NUMBER_RE.search(text.replace("\u00a0", " "))
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None


def parse_region(value: Any) -> tuple[str | None, str | None]:
    """Return (city_name, region_name) per aurora-field-mapping rules."""
    text = _as_text(value)
    if not text:
        return None, None
    if "|" in text:
        left, right = text.split("|", 1)
        city = left.strip() or None
        region = right.strip() or None
        return city, region
    lowered = text.lower()
    if lowered.startswith("г.") or lowered.startswith("г "):
        return text, None
    return None, text


def decode_csv_bytes(data: bytes) -> tuple[str, str]:
    """Decode CSV bytes.

    Prefer UTF-8 when the payload is valid UTF-8 (avoids silent cp1251 mojibake).
    Live Aurora export is cp1251 and fails UTF-8 decode → fall back to cp1251.
    """
    if not data:
        raise ProviderParseError("Aurora CSV body is empty")
    try:
        return data.decode(contract.FALLBACK_ENCODING), contract.FALLBACK_ENCODING
    except UnicodeDecodeError:
        pass
    try:
        return data.decode(contract.PRIMARY_ENCODING), contract.PRIMARY_ENCODING
    except UnicodeDecodeError as exc:
        raise ProviderParseError(
            f"Aurora CSV decode failed ({contract.PRIMARY_ENCODING}/"
            f"{contract.FALLBACK_ENCODING}): {exc}"
        ) from exc


def normalize_row(row: list[str], *, filename: str | None = None) -> list[str]:
    """Normalize provider row shape before the 5-column contract check.

    MSK.csv currently inserts a status column (e.g. СВОБОДЕН) at index 1.
    Drop that column when the row has exactly 6 fields so classic mapping applies.
    """
    if not row:
        return row
    name = (filename or "").rsplit("/", 1)[-1].lower()
    if name == "msk.csv" and len(row) == 6:
        return [row[0], *row[2:]]
    return row


def parse_probe_bytes(
    data: bytes,
    *,
    truncated: bool = False,
    filename: str | None = None,
) -> tuple[ParsedNumberItem | None, dict[str, Any]]:
    """Parse first valid free-number row from a CSV head sample."""
    text, encoding = decode_csv_bytes(data)
    # Stream probe may cut mid-row; drop the trailing incomplete line when truncated.
    if truncated or (data and not data.endswith((b"\n", b"\r"))):
        cut = max(text.rfind("\n"), text.rfind("\r"))
        if cut >= 0:
            text = text[:cut]
    reader = csv.reader(io.StringIO(text), delimiter=contract.CSV_DELIMITER)
    scanned = 0
    for row in reader:
        if not row or all(not (c or "").strip() for c in row):
            continue
        scanned += 1
        normalized = normalize_row(row, filename=filename)
        if len(normalized) != contract.EXPECTED_COLUMNS:
            continue
        parsed = parse_row(normalized, original_column_count=len(row))
        if parsed:
            return parsed, {
                "encoding": encoding,
                "scanned_rows": scanned,
                "sample_msisdn": parsed.msisdn,
            }
    return None, {"encoding": encoding, "scanned_rows": scanned}


def parse_csv_text(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=contract.CSV_DELIMITER)
    rows: list[list[str]] = []
    for row in reader:
        if not row or all(not (c or "").strip() for c in row):
            continue
        rows.append(row)
    return rows


def row_to_raw_payload(
    row: list[str],
    *,
    original_column_count: int | None = None,
) -> dict[str, Any]:
    phone = row[contract.COL_PHONE] if len(row) > contract.COL_PHONE else ""
    number_type = row[contract.COL_TYPE] if len(row) > contract.COL_TYPE else ""
    fee = row[contract.COL_FEE] if len(row) > contract.COL_FEE else ""
    region = row[contract.COL_REGION] if len(row) > contract.COL_REGION else ""
    display_mask = (
        row[contract.COL_DISPLAY_MASK] if len(row) > contract.COL_DISPLAY_MASK else ""
    )
    city_name, region_name = parse_region(region)
    column_count = (
        original_column_count if original_column_count is not None else len(row)
    )
    payload: dict[str, Any] = {
        "phone_raw": phone,
        "number_type": number_type,
        "period_price_raw": fee,
        "region_raw": region,
        "display_mask": display_mask,
        "city_name": city_name,
        "region_name": region_name,
        "column_count": column_count,
    }
    if original_column_count == 6 and len(row) == contract.EXPECTED_COLUMNS:
        payload["dropped_status_column"] = True
    return payload


def parse_row(
    row: list[str],
    *,
    original_column_count: int | None = None,
) -> ParsedNumberItem | None:
    if len(row) < contract.EXPECTED_COLUMNS:
        return None
    payload = row_to_raw_payload(row, original_column_count=original_column_count)
    msisdn = normalize_phone(payload["phone_raw"])
    if not msisdn or not (len(msisdn) == 11 and msisdn.startswith("7")):
        return None
    city_name = payload["city_name"]
    region_name = payload["region_name"]
    return ParsedNumberItem(
        raw_payload=payload,
        provider_number_key=msisdn,
        msisdn=msisdn,
        city_name=city_name if isinstance(city_name, str) else None,
        region_name=region_name if isinstance(region_name, str) else None,
        period_price=parse_period_price(payload["period_price_raw"]),
        number_type=_as_text(payload["number_type"]),
        display_mask=_as_text(payload["display_mask"]),
    )


def parse_free_csv(
    raw: RawHttpResult,
    *,
    raw_bytes: bytes | None = None,
    filename: str | None = None,
) -> tuple[
    list[ParsedNumberItem],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Parse free CSV into items + unmapped raw rows + meta."""
    if raw.status_code >= 400:
        raise ProviderParseError(f"Aurora HTTP {raw.status_code}")
    data = raw_bytes if raw_bytes is not None else raw.body_text.encode("latin-1")
    text, encoding = decode_csv_bytes(data)
    rows = parse_csv_text(text)
    items: list[ParsedNumberItem] = []
    unmapped: list[dict[str, Any]] = []
    source_name = filename or contract.csv_filename(raw.request_url or "")
    for row in rows:
        normalized = normalize_row(row, filename=source_name)
        if len(normalized) != contract.EXPECTED_COLUMNS:
            unmapped.append(
                row_to_raw_payload(row, original_column_count=len(row))
                if row
                else {"column_count": 0}
            )
            continue
        parsed = parse_row(normalized, original_column_count=len(row))
        if parsed:
            items.append(parsed)
        else:
            unmapped.append(
                row_to_raw_payload(normalized, original_column_count=len(row))
            )
    meta = {
        "encoding": encoding,
        "row_count": len(rows),
        "parsed": len(items),
        "unmapped": len(unmapped),
        "file": source_name or None,
    }
    return items, unmapped, meta
