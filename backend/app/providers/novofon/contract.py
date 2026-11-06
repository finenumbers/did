"""Novofon Data API machine contract. Mirror: docs/providers/novofon-contract.md."""

EXAMPLE_BASE_URL = "https://dataapi-jsonrpc.novofon.ru/v2.0"

METHOD_AVAILABLE_VIRTUAL_NUMBERS = "get.available_virtual_numbers"
METHOD_VIRTUAL_NUMBERS = "get.virtual_numbers"
METHOD_ACCOUNT = "get.account"
METHOD_CUSTOMER_USERS = "get.customer_users"

# How many customer users to name when an agent key has no user_id.
USER_PREVIEW_LIMIT = 20

AUTH_ACCESS_TOKEN = "access_token"
AUTH_USER_ID = "user_id"
# Classic User API. Optional: the Novofon 2.0 cabinet does not show Key.
AUTH_API_KEY = "api_key"
AUTH_API_SECRET = "api_secret"

# Order shop. Not the Data API host and not connection.base_url.
USER_API_BASE_URL = "https://api.novofon.com"
USER_API_COUNTRIES = "/v1/direct_numbers/countries/"
USER_API_COUNTRY = "/v1/direct_numbers/country/"
USER_API_AVAILABLE = "/v1/direct_numbers/available/"
# Already connected direct numbers. Read when Key is set. Not the order shop.
USER_API_OWNED = "/v1/direct_numbers/"
USER_API_LANGUAGE = "ru"
USER_API_CONNECT_TIMEOUT = 10.0
USER_API_READ_TIMEOUT = 30.0
# Used only when the response has no X-RateLimit-* headers.
USER_API_PACE_SECONDS = 1.2
USER_API_RETRY_MAX_SECONDS = 120

KEY_MISSING_MESSAGE = (
    "Витрина заказа не запрашивалась: в кабинете Новофон 2.0 нет отдельного Key, "
    "только один ключ Data API (Access token)."
)

# VERIFIED pagination. Product page sizes differ by method (operational).
FREE_PAGE_LIMIT = 10_000
PURCHASED_PAGE_LIMIT = 1_000
MAX_LIMIT = 10_000
MAX_OFFSET = 100_000

# VERIFIED category enums. Null is a separate slice (operator "=", value null).
FREE_CATEGORIES = ("usual", "bronze", "silver", "gold")
PURCHASED_CATEGORIES = ("usual", "bronze", "silver", "gold", "platinum")

JSONRPC_VERSION = "2.0"

# One minute-limit retry. Day limit is not retried.
LIMIT_RETRY_MAX_SECONDS = 120
