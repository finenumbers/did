"""Novofon Data API machine contract. Mirror: docs/providers/novofon-contract.md."""

EXAMPLE_BASE_URL = "https://dataapi-jsonrpc.novofon.ru/v2.0"

METHOD_AVAILABLE_VIRTUAL_NUMBERS = "get.available_virtual_numbers"
METHOD_VIRTUAL_NUMBERS = "get.virtual_numbers"

AUTH_ACCESS_TOKEN = "access_token"
AUTH_USER_ID = "user_id"

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
