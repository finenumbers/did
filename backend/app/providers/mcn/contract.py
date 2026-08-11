"""
MCN Telecom Витрина contract — mirrors docs/providers/mcn-contract.md
"""

EXAMPLE_BASE_URL = "https://shop.mcn.ru"

AUTH_API_KEY = "api_key"
AUTH_HEADER_MODE = "auth_header_mode"

# VERIFIED ISO numeric country code for Russia in showcase API
COUNTRY_CODE_RU = 643

PATH_COUNTRIES = "/api/protected/showcase/countries"
PATH_REGIONS = "/api/protected/showcase/regions"
PATH_CITIES = "/api/protected/showcase/cities"
PATH_NUMBERS = "/api/protected/showcase/numbers"

# VERIFIED OpenAPI default
DEFAULT_PAGE_LIMIT = 25
# OPERATIONAL probes (max not documented)
PAGE_LIMIT_PROBES: tuple[int, ...] = (25, 100, 200)
MAX_PAGE_NUMBER = 500_000
MAX_SLICE_CONCURRENCY = 3

AUTH_MODE_BEARER = "bearer"
AUTH_MODE_RAW = "raw"
AUTH_MODE_X_AUTH = "x_auth_token"
AUTH_MODE_CANDIDATES: tuple[str, ...] = (
    AUTH_MODE_BEARER,
    AUTH_MODE_RAW,
    AUTH_MODE_X_AUTH,
)

STATUS_FREE = "free"

DOC_REFS_VITRINA = [
    "https://apidocs.mcn.ru/api/projects/31/docs",
    "https://shop.mcn.ru/api/openapi/protected-json",
]
DOC_REFS_TOKEN = [
    "https://help.mcn.ru/ru-RU/support/solutions/articles/43000715053",
]
