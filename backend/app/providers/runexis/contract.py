"""
Runexis machine contract — mirrors docs/providers/runexis-contract.md
Source: docs/providers/runexis/raw/Runexis.html
"""

# VERIFIED: Introduction Base URL
EXAMPLE_BASE_URL = "https://didapi.runexis.ru"

# VERIFIED: Authenticating requests
AUTH_HEADER = "Authorization"
AUTH_SCHEME = "Bearer"

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

# Capability limitations (no free/purchased inventory endpoints in docs)
FREE_NUMBERS_SUPPORTED = False
PURCHASED_NUMBERS_SUPPORTED = False
DOC_REFS_LIMITATIONS = [
    "docs/providers/runexis-contract.md#limitations",
    "docs/providers/runexis-field-mapping.md",
]
