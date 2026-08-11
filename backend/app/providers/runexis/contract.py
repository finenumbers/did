"""
Runexis machine contract — mirrors docs/providers/runexis-contract.md
Sources:
- DIDAPI: docs/providers/runexis/raw/Runexis.html
- Numbering (free catalog): docs/providers/runexis/raw/Runexis-Numbering-API.docx
"""

# VERIFIED: Introduction Base URL (DIDAPI)
EXAMPLE_BASE_URL = "https://didapi.runexis.ru"

# VERIFIED: Numbering API base (Runexis-Numbering-API.docx)
NUMBERING_EXAMPLE_BASE_URL = "https://did-api.runexis.ru/"
NUMBERING_METHOD_CONNECT = "connect"
NUMBERING_METHOD_SEARCH = "search_numbers"
NUMBERING_METHOD_SEARCH_COUNT = "search_numbers_count"
# Auth settings keys (separate from DIDAPI email/password)
AUTH_NUMBERING_LOGIN = "numbering_login"
AUTH_NUMBERING_PASSWORD = "numbering_password"
AUTH_NUMBERING_PARTITION = "numbering_partition"
AUTH_NUMBERING_SESSION = "numbering_session_id"
AUTH_NUMBERING_BASE_URL = "numbering_base_url"
# VERIFIED filter field name; EXAMPLE-CONFIRMED alternate key usage_statuses in same DOCX
NUMBERING_FREE_FILTER_PRIMARY = {"access_state": ["free"]}
NUMBERING_FREE_FILTER_FALLBACK = {"usage_statuses": ["free"]}
# Client-side allow-list after search_numbers (API may return non-free despite filter).
# Only these values enter inventory_kind=free. Purchased stays on DIDAPI management.
NUMBERING_FREE_STATUS_VALUES = frozenset({"free", "0"})
# Live: ~40s/page regardless of size; 20k ≈ 17–22 pages for free list
NUMBERING_PAGE_LIMIT = 20_000
# Parallel search_numbers pages (all-or-nothing; lower if API rate-limits)
NUMBERING_FETCH_CONCURRENCY = 6
# search_numbers_count is a progress upper bound (API total), not free-list size
NUMBERING_SOURCE_ENDPOINT = "numbering-api:search_numbers"
# Numbering search is slow; defaults in TimeoutConfig are too short
NUMBERING_CONNECT_TIMEOUT = 30.0
NUMBERING_READ_TIMEOUT = 300.0
NUMBERING_TOTAL_TIMEOUT = 330.0
DOC_REFS_NUMBERING_FREE = [
    "docs/providers/runexis-numbering-api-contract.md",
    "docs/providers/runexis/raw/Runexis-Numbering-API.docx",
]

# VERIFIED: Authenticating requests
AUTH_HEADER = "Authorization"
AUTH_SCHEME = "Bearer"

# VERIFIED Auth paths (login body: email+password; refresh body field "token" = refresh_token)
POST_LOGIN = "api/v1/login"
POST_REFRESH = "api/v1/refresh"

# EXAMPLE-CONFIRMED auth token response keys under data
EXAMPLE_AUTH_TOKEN_KEYS = frozenset(
    {"token", "refresh_token", "token_expire", "refresh_token_expire"}
)

# VERIFIED paths
GET_ME = "api/v1/me"
GET_REGIONS = "api/v1/regions"
GET_CITIES = "api/v1/regions/cities"
GET_REGION_CODES = "api/v1/regions/codes"
GET_NUMBERS = "api/v1/numbers"
GET_NUMBERS_MANAGEMENT = "api/v1/numbers/management"
POST_NUMBERS_LOAD_DATA = "api/v1/numbers/load-data"
GET_NUMBERS_LOAD_DATA = "api/v1/numbers/load-data"

# EXAMPLE-CONFIRMED response keys
EXAMPLE_REGION_KEYS = frozenset({"id", "name"})
EXAMPLE_CITY_KEYS = frozenset({"city_id", "city_name", "region_id", "region_name"})
EXAMPLE_MANAGEMENT_KEYS = frozenset(
    {"id", "code", "number", "status", "city", "tariff", "installationCost", "subscriptionFee", "meraPrice"}
)

# Inventory sync from management list (VERIFIED path)
FREE_NUMBERS_SUPPORTED = True
PURCHASED_NUMBERS_SUPPORTED = True
# EXAMPLE-CONFIRMED: docs example pairs number_status_id=1 with status.mnemonic=free
NUMBER_STATUS_ID_FREE = 1
STATUS_MNEMONIC_FREE = "free"
MANAGEMENT_PAGE_LIMIT = 100
DOC_REFS_INVENTORY = [
    "docs/providers/runexis-contract.md",
    "docs/providers/runexis-field-mapping.md",
]
