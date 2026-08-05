"""Aurora Telecom machine contract — mirrors docs/providers/aurora-contract.md."""

from __future__ import annotations

from urllib.parse import urlparse, urljoin

DEFAULT_CSV_BASE = "http://bill.auroratelecom.ru:8080/bgbilling/numbers/"
# Regional free exports — all_free.csv is NOT used.
DEFAULT_CSV_FILES: tuple[str, ...] = (
    "Crimea.csv",
    "Grozny.csv",
    "MSK.csv",
    "Sevastopol.csv",
    "Simferopol.csv",
    "SPb.csv",
)
# Legacy alias: dirname of a single .csv Settings URL becomes the base.
EXAMPLE_BASE_URL = DEFAULT_CSV_BASE
# Back-compat name used in older tests/docs references (directory, not a file).
DEFAULT_CSV_URL = DEFAULT_CSV_BASE

PRIMARY_ENCODING = "cp1251"
FALLBACK_ENCODING = "utf-8-sig"
CSV_DELIMITER = ";"
EXPECTED_COLUMNS = 5
# Operational safety cap per file
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


def resolve_csv_urls(base_url: str | None) -> list[str]:
    """
    Build the fixed regional CSV URL list.

    - empty → DEFAULT_CSV_BASE + DEFAULT_CSV_FILES
    - URL ending in .csv (incl. legacy all_free.csv) → parent directory + FILES
      (the named .csv itself is never fetched)
    - otherwise → treat as directory prefix + FILES
    """
    raw = (base_url or "").strip()
    if not raw:
        base = DEFAULT_CSV_BASE
    elif raw.lower().endswith(".csv"):
        # dirname; keep trailing slash for urljoin
        parent = raw.rsplit("/", 1)[0]
        base = parent + "/" if parent else DEFAULT_CSV_BASE
    else:
        base = raw if raw.endswith("/") else raw + "/"

    return [urljoin(base, name) for name in DEFAULT_CSV_FILES]


def csv_filename(url: str) -> str:
    path = urlparse(url).path or ""
    return path.rsplit("/", 1)[-1] or url
