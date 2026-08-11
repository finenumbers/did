"""
Voximplant Management API contract — mirrors docs/providers/voximplant-contract.md
"""

EXAMPLE_BASE_URL = "https://api.voximplant.com"

AUTH_ACCOUNT_ID = "account_id"
AUTH_KEY_ID = "key_id"
AUTH_PRIVATE_KEY = "private_key"
AUTH_CREDENTIALS_JSON = "credentials_json"

COUNTRY_CODE_RU = "RU"
SANDBOX_REAL = "false"
LOCALE_RU = "RU"

METHOD_GET_ACCOUNT_INFO = "GetAccountInfo"
METHOD_GET_CATEGORIES = "GetPhoneNumberCategories"
METHOD_GET_REGIONS = "GetPhoneNumberRegions"
METHOD_GET_NEW_PHONES = "GetNewPhoneNumbers"

# VERIFIED docs default for GetNewPhoneNumbers.count
DEFAULT_PAGE_LIMIT = 20
MAX_OFFSET = 5_000_000
# OPERATIONAL — keep low due to error 314 CONCURRENT_RESOURCE_LIMIT_EXCEEDED
MAX_SLICE_CONCURRENCY = 3
JWT_TTL_SECONDS = 3600
JWT_REFRESH_SKEW_SECONDS = 60

STATUS_FREE = "free"

DOC_REFS_AUTH = [
    "https://docs.voximplant.ai/api-reference/management-api/authorization",
]
DOC_REFS_FREE = [
    "https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers/get-new-phone-numbers",
]
DOC_REFS_REFERENCE = [
    "https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers/get-phone-number-categories",
    "https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers/get-phone-number-regions",
]
