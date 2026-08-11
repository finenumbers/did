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

# OPERATIONAL — docs do not state max page size; raise after live probe if needed
DEFAULT_PAGE_LIMIT = 100
MAX_OFFSET = 5_000_000

# OPERATIONAL — omit random by default (docs examples use true; false seen empty in prod)
DEFAULT_RANDOM_MODE = "omit"

STATUS_FREE = "free"

DOC_REFS_FREE = [
    "https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/",
]
DOC_REFS_REFERENCE = [
    "https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/",
]
