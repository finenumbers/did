"""Aurora Telecom machine contract — mirrors docs/providers/aurora-contract.md."""

DEFAULT_CSV_URL = "http://bill.auroratelecom.ru:8080/bgbilling/numbers/all_free.csv"
EXAMPLE_BASE_URL = DEFAULT_CSV_URL

PRIMARY_ENCODING = "cp1251"
FALLBACK_ENCODING = "utf-8-sig"
CSV_DELIMITER = ";"
EXPECTED_COLUMNS = 5
# Operational safety cap (live export is ~4–5 MB)
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
