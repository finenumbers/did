"""DIDWW API v3 contract — mirrors docs/providers/didww-contract.md.

Canonical attribute names: DIDWW object pages (VERIFIED).
Example JSON on Get DID Groups diverges — parser accepts aliases (EXAMPLE-CONFIRMED).
"""

from __future__ import annotations

EXAMPLE_BASE_URL = "https://api.didww.com/v3"
SANDBOX_BASE_URL = "https://sandbox-api.didww.com/v3"

AUTH_API_KEY = "api_key"
# Getting Started: header `Api-Key`. Other pages show `Api-Key`. Live canary locks OPERATIONAL.
API_KEY_HEADER = "Api-Key"
ACCEPT = "application/vnd.api+json"
CONTENT_TYPE = "application/vnd.api+json"
API_VERSION_HEADER = "X-Didww-Api-Version"
API_VERSION = "2026-04-16"

# VERIFIED Getting Started: 20 rps → 429
MAX_RPS = 10
REQUEST_GAP_SECONDS = 0.12
RETRY_ON_STATUS = (429, 502, 503, 504)

PATH_COUNTRIES = "/countries"
PATH_REGIONS = "/regions"
PATH_CITIES = "/cities"
PATH_DID_GROUP_TYPES = "/did_group_types"
PATH_DID_GROUPS = "/did_groups"
PATH_BALANCE = "/balance"
PATH_AVAILABLE_DIDS = "/available_dids"

# VERIFIED Get Cities: default and max page size 1000
CITIES_PAGE_SIZE = 1000
# VERIFIED pagination spec: default 50, max 100 unless overridden
DID_GROUPS_PAGE_SIZE = 100
REGIONS_PAGE_SIZE = 100
TYPES_PAGE_SIZE = 100

# VERIFIED Get DID Groups includes table
DID_GROUPS_INCLUDE = "country,region,city,did_group_type,stock_keeping_units"
REGIONS_INCLUDE = "country"
CITIES_INCLUDE = "country,region"
AVAILABLE_DIDS_INCLUDE = "did_group,did_group.stock_keeping_units"

# VERIFIED Get DID Groups filter
FILTER_IN_STOCK = "filter[is_available]"

# JSON:API types (VERIFIED object pages / examples)
TYPE_COUNTRIES = "countries"
TYPE_REGIONS = "regions"
TYPE_CITIES = "cities"
TYPE_DID_GROUP_TYPES = "did_group_types"
TYPE_DID_GROUPS = "did_groups"
TYPE_SKUS = "stock_keeping_units"
TYPE_AVAILABLE_DIDS = "available_dids"

DOC_REFS = {
    "getting_started": "https://doc.didww.com/api3/configuration.html",
    "did_groups": "https://doc.didww.com/api3/2026-04-16/coverage-resources/did-group/get-did-groups.html",
    "did_group_object": "https://doc.didww.com/api3/2026-04-16/coverage-resources/did-group/did-group-object.html",
    "sku": "https://doc.didww.com/api3/2026-04-16/common-definitions/stock-keeping-unit-object.html",
    "available_dids": "https://doc.didww.com/api3/2026-04-16/coverage-resources/available-did/get-available-dids.html",
}

# Parser aliases: canonical first (object page), then example JSON keys.
SKU_SETUP_KEYS = ("setup_price", "setup_price")
SKU_MONTHLY_KEYS = ("monthly_price", "monthly_price")
SKU_CHANNELS_KEYS = ("channels_included_count", "channels_included_count")
META_AVAILABLE_KEYS = ("is_available", "is_available")
META_STOCK_KEYS = ("total_count", "total_count")
META_PICKER_KEYS = ("available_dids_enabled", "available_dids_enabled")
META_KYC_KEYS = ("needs_registration", "needs_registration")
ATTR_AREA_KEYS = ("area_name", "area_name")
ATTR_METERED_KEYS = ("is_metered", "is_metered")
ATTR_CHANNELS_KEYS = ("allow_additional_channels", "allow_additional_channels")
ATTR_RESTRICTIONS_KEYS = ("service_restrictions", "service_restrictions")
COUNTRY_ISO_KEYS = ("iso", "iso")
SKU_REL_KEYS = ("stock_keeping_units", "stock_keeping_units")
SKU_INCLUDED_TYPES = (TYPE_SKUS, "stock_keeping_units")
