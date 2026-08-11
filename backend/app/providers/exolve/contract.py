"""
Exolve Numbering API contract — mirrors docs/providers/exolve-contract.md
"""

EXAMPLE_BASE_URL = "https://api.exolve.ru"

AUTH_API_KEY = "api_key"

PATH_REFERENCE = "/number/reference/v1/GetList"
PATH_GET_FREE = "/number/v1/GetFree"

# VERIFIED docs: type_id values
TYPE_DEF = 1104
TYPE_ABC = 1105
TYPE_KDU = 1106
SYNC_TYPE_IDS: tuple[int, ...] = (TYPE_DEF, TYPE_ABC, TYPE_KDU)

TYPE_NAMES: dict[int, str] = {
    TYPE_DEF: "DEF",
    TYPE_ABC: "ABC",
    TYPE_KDU: "KDU",
}

# VERIFIED docs: KDU only with Russia
RUSSIA_REGION_ID = 10084

# VERIFIED docs GetFree examples (Numbering API + buying-number instruction)
DOC_EXAMPLE_MOSCOW_DEF = {
    "type_id": TYPE_DEF,
    "region_id": 10230,
    "category_id": 10000,  # Обычный / mobile
    "random": True,
    "limit": 1,
}
DOC_EXAMPLE_MOSCOW_ABC = {
    "type_id": TYPE_ABC,
    "region_id": 10230,
    "category_id": 10001,  # Обычный / city (buying-number Postman)
    "random": True,
    "limit": 1,
}

# VERIFIED docs category table (fallback if GetList categories empty for a type)
DOC_CATEGORY_IDS_BY_TYPE: dict[int, tuple[int, ...]] = {
    TYPE_DEF: (10000, 10010, 10020, 10030, 10040, 10050),
    TYPE_ABC: (10001, 10011, 10021, 10031, 10041, 10051),
    TYPE_KDU: (10002, 10012, 10022, 10032, 10042, 10052),
}

# OPERATIONAL — docs do not state max page size; raise after live probe if needed
DEFAULT_PAGE_LIMIT = 100
MAX_OFFSET = 5_000_000

# OPERATIONAL — omit random by default for inventory pagination
DEFAULT_RANDOM_MODE = "omit"

# Sync slice modes (chosen from live canary)
SYNC_MODE_TYPE_REGION = "type_region"
SYNC_MODE_TYPE_REGION_CATEGORY = "type_region_category"

STATUS_FREE = "free"

DOC_REFS_FREE = [
    "https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/",
    "https://docs.exolve.ru/docs/ru/instructions/buying-number/",
]
DOC_REFS_REFERENCE = [
    "https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/",
]
