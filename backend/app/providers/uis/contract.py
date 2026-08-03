"""UIS Data API machine contract. Mirror: docs/providers/uis-contract.md."""

# VERIFIED: https://dataapi.uiscom.ru/v2.0 (not comagic.ru)
EXAMPLE_BASE_URL = "https://dataapi.uiscom.ru/v2.0"

# VERIFIED methods (read-only for DID)
METHOD_LOGIN_USER = "login.user"
METHOD_AVAILABLE_VIRTUAL_NUMBERS = "get.available_virtual_numbers"
METHOD_VIRTUAL_NUMBERS = "get.virtual_numbers"

# Auth settings keys
AUTH_ACCESS_TOKEN = "access_token"
AUTH_LOGIN = "login"
AUTH_PASSWORD = "password"
AUTH_USER_ID = "user_id"
AUTH_SESSION_EXPIRE_AT = "session_expire_at"

# VERIFIED pagination defaults/max
DEFAULT_LIMIT = 1000
MAX_LIMIT = 10_000
MAX_OFFSET = 100_000

JSONRPC_VERSION = "2.0"
