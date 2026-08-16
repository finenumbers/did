"""Finenumbers PSTN + REG (Contour C) contracts."""

# Contour A — PSTN inventory
EXAMPLE_BASE_URL = "https://pstn.finenumbers.com"
AUTH_SETTINGS_KEY = "key"
OPERATOR_INN = "5406978329"
OPERATOR_DISPLAY_NAME = "ООО «Фронтир Нетворк»"
BY_INN_PATH = "/api/v1/lookup/by-inn"
LOOKUP_PATH = "/api/v1/lookup"
DEFAULT_PAGE_SIZE = 100
# Keep a small headroom under the documented platform cap (5000/min)
RATE_LIMIT_SAFE_PER_MINUTE = 4800
# Refuse Contour A expand if materialised MSISDNs would exceed this (OOM guard)
MAX_EXPAND_NUMBERS = 2_000_000

# Contour C — REG purchased / RTU connectivity (sibling project Reg, read-only)
REG_EXAMPLE_BASE_URL = "https://reg.finenumbers.com"
REG_AUTH_SETTINGS_KEY = "reg_key"
REG_BASE_URL_EXTRA_KEY = "reg_base_url"
REG_PHONES_PATH = "/api/phones"
REG_PHONE_KINDS = (
    "endpoints_registered",
    "endpoints_unregistered",
    "endpoints_error",
)
REG_DEFAULT_PAGE_SIZE = 100
REG_MAX_PAGE_SIZE = 200
# Documented Reg API key limit 10000/min — stay under
REG_RATE_LIMIT_SAFE_PER_MINUTE = 9000

# Catalog column «Подключено в РТУ» (purchased only)
RTU_OWN = "Своя нумерация"
RTU_EXTERNAL = "Внешняя нумерация"
RTU_NOT_CONNECTED = "Не подключено"
