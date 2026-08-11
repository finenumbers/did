"""Finenumbers PSTN lookup API contract."""

EXAMPLE_BASE_URL = "https://pstn.finenumbers.com"
AUTH_SETTINGS_KEY = "key"
OPERATOR_INN = "5406978329"
BY_INN_PATH = "/api/v1/lookup/by-inn"
LOOKUP_PATH = "/api/v1/lookup"
DEFAULT_PAGE_SIZE = 100
# Keep a small headroom under the documented platform cap (5000/min)
RATE_LIMIT_SAFE_PER_MINUTE = 4800
# Refuse Contour A expand if materialised MSISDNs would exceed this (OOM guard)
MAX_EXPAND_NUMBERS = 2_000_000
