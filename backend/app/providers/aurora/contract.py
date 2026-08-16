"""Aurora Telecom machine contract — mirrors docs/providers/aurora-contract.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

from app.providers.errors import ProviderError

ALLOWED_HOST = "bill.auroratelecom.ru"
DEFAULT_CSV_BASE = "http://bill.auroratelecom.ru:8080/bgbilling/numbers/"
# Seed / one-shot backfill only — NOT used at runtime sync/client resolve.
_SEED_FILENAMES: tuple[tuple[str, bool], ...] = (
    ("Crimea.csv", False),
    ("Grozny.csv", False),
    ("MSK.csv", True),
    ("Sevastopol.csv", False),
    ("Simferopol.csv", False),
    ("SPb.csv", False),
)
EXAMPLE_BASE_URL = DEFAULT_CSV_BASE

PRIMARY_ENCODING = "cp1251"
FALLBACK_ENCODING = "utf-8-sig"
CSV_DELIMITER = ";"
EXPECTED_COLUMNS = 5
MAX_CSV_BYTES = 32 * 1024 * 1024

COL_PHONE = 0
COL_TYPE = 1
COL_FEE = 2
COL_REGION = 3
COL_DISPLAY_MASK = 4

DOC_REFS = [
    "docs/providers/aurora-contract.md",
    "docs/providers/aurora-field-mapping.md",
    "docs/providers/aurora/SOURCE.md",
]


@dataclass(frozen=True)
class CsvFileEntry:
    url: str
    has_status_column: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "has_status_column": self.has_status_column}


def csv_filename(url: str) -> str:
    path = urlparse(url).path or ""
    return path.rsplit("/", 1)[-1] or url


def seed_csv_files() -> list[CsvFileEntry]:
    """Canonical starter list for new installs and empty-connection backfill."""
    return [
        CsvFileEntry(url=urljoin(DEFAULT_CSV_BASE, name), has_status_column=flag)
        for name, flag in _SEED_FILENAMES
    ]


def _legacy_urls_from_base(base_url: str | None) -> list[str]:
    """One-shot backfill helper only. Do not call from sync/client runtime."""
    raw = (base_url or "").strip()
    if not raw:
        base = DEFAULT_CSV_BASE
    elif raw.lower().endswith(".csv"):
        parent = raw.rsplit("/", 1)[0]
        base = parent + "/" if parent else DEFAULT_CSV_BASE
    else:
        base = raw if raw.endswith("/") else raw + "/"
    return [urljoin(base, name) for name, _ in _SEED_FILENAMES]


def legacy_backfill_entries(base_url: str | None) -> list[CsvFileEntry]:
    """Build csv_files from legacy directory/base_url (MSK flagged by filename)."""
    entries: list[CsvFileEntry] = []
    for url in _legacy_urls_from_base(base_url):
        name = csv_filename(url).lower()
        entries.append(CsvFileEntry(url=url, has_status_column=(name == "msk.csv")))
    return entries


def validate_csv_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ProviderError("Aurora CSV URL is empty", code="AURORA_CSV_INVALID")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ProviderError(
            f"Aurora URL scheme not allowed: {parsed.scheme!r}",
            code="AURORA_CSV_INVALID",
        )
    host = (parsed.hostname or "").lower()
    if host != ALLOWED_HOST:
        raise ProviderError(
            f"Aurora URL host not allowed: {host!r} (expected {ALLOWED_HOST})",
            code="AURORA_CSV_INVALID",
        )
    name = (parsed.path or "").rsplit("/", 1)[-1].lower()
    if not name.endswith(".csv"):
        raise ProviderError(
            f"Aurora URL must end with .csv: {raw!r}",
            code="AURORA_CSV_INVALID",
        )
    if name == "all_free.csv":
        raise ProviderError(
            "Aurora all_free.csv is not used; add regional CSV file URLs in Settings",
            code="AURORA_CSV_INVALID",
        )
    return raw


def parse_csv_file_entry(raw: Any) -> CsvFileEntry:
    if isinstance(raw, str):
        url = validate_csv_url(raw)
        return CsvFileEntry(url=url, has_status_column=False)
    if not isinstance(raw, dict):
        raise ProviderError(
            "Aurora csv_files entry must be an object with url",
            code="AURORA_CSV_INVALID",
        )
    url = validate_csv_url(str(raw.get("url") or ""))
    flag = bool(raw.get("has_status_column"))
    return CsvFileEntry(url=url, has_status_column=flag)


def normalize_csv_files(raw_list: Any, *, require_non_empty: bool = True) -> list[CsvFileEntry]:
    if raw_list is None:
        entries: list[CsvFileEntry] = []
    elif not isinstance(raw_list, list):
        raise ProviderError(
            "Aurora extra_settings.csv_files must be a list",
            code="AURORA_CSV_INVALID",
        )
    else:
        entries = [parse_csv_file_entry(item) for item in raw_list]

    seen: set[str] = set()
    unique: list[CsvFileEntry] = []
    for entry in entries:
        key = entry.url.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)

    if require_non_empty and not unique:
        raise ProviderError(
            "Aurora csv_files is empty; add at least one CSV URL in Settings",
            code="AURORA_CSV_EMPTY",
        )
    return unique


def load_csv_files(extra_settings: dict[str, Any] | None) -> list[CsvFileEntry]:
    """Runtime source of truth: extra_settings.csv_files only."""
    extra = extra_settings or {}
    return normalize_csv_files(extra.get("csv_files"), require_non_empty=True)


def csv_files_configured(extra_settings: dict[str, Any] | None) -> bool:
    extra = extra_settings or {}
    raw = extra.get("csv_files")
    return isinstance(raw, list) and len(raw) > 0
