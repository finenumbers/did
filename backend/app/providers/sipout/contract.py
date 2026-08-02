"""
SipOut machine contract — mirrors docs/providers/sipout-contract.md
Source: docs/providers/sipout/raw/SipOut.html
"""

# VERIFIED: Основные положения — URL form
EXAMPLE_BASE_URL = "https://lk.sipout.net/userapi/"

# VERIFIED: Ваш api-ключ / Основные положения
AUTH_QUERY_PARAM = "key"

# VERIFIED: method=did (Городские номера)
METHOD_DID = "did"
ACTION_FREE_LIST = "free_list"  # VERIFIED: Свободные номера
ACTION_CONNECTED_LIST = "connected_list"  # VERIFIED: Список подключенных номеров
ACTION_GET_CITIES = "get_cities"  # VERIFIED: Список городов

# VERIFIED: Текущий баланс
METHOD_BALANCE = "balance"
ACTION_BALANCE_GET = "get"

# VERIFIED: free_list optional GET params
FREE_LIST_PARAM_CITY_ID = "city_id"
FREE_LIST_PARAM_MASK = "mask"

# VERIFIED: formal response containers
FORMAL_LIST_KEYS = frozenset({"cnt", "list"})
FORMAL_GEO_KEYS = frozenset({"cities", "regions"})

# EXAMPLE-CONFIRMED item keys (not formal schema)
EXAMPLE_FREE_ITEM_KEYS = frozenset({"did", "price", "city_id"})
EXAMPLE_CONNECTED_ITEM_KEYS = frozenset(
    {
        "did",
        "user_comment",
        "order_id",
        "doc_status",
        "order_doc_required",
        "doc_required",
        "status",
        "city_id",
        "has_sms",
        "sign",
    }
)
EXAMPLE_CITY_KEYS = frozenset({"id", "name", "eng_name", "region_id"})
EXAMPLE_REGION_KEYS = frozenset({"id", "name", "capital_city", "eng_name", "gmt"})
