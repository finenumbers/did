"""UIS Data API machine contract. Mirror: docs/providers/uis-contract.md."""

# VERIFIED: https://dataapi.uiscom.ru/v2.0 (not comagic.ru)
EXAMPLE_BASE_URL = "https://dataapi.uiscom.ru/v2.0"

# VERIFIED methods used by DID (read-only get.*; product auth = API key)
METHOD_AVAILABLE_VIRTUAL_NUMBERS = "get.available_virtual_numbers"
METHOD_VIRTUAL_NUMBERS = "get.virtual_numbers"

# Auth settings keys (product: access_token only; login.user not used)
AUTH_ACCESS_TOKEN = "access_token"
AUTH_USER_ID = "user_id"

# VERIFIED pagination defaults/max (docs allow up to MAX_LIMIT)
DEFAULT_LIMIT = 10_000
MAX_LIMIT = 10_000
MAX_OFFSET = 100_000

JSONRPC_VERSION = "2.0"
