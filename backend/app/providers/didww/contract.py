"""DIDWW API v3 contract — mirrors docs/providers/didww-contract.md.

Field names are taken from the versioned object pages of API version 2026-04-16
(VERIFIED); the JSON examples on the same pages use exactly the same keys.
"""

from __future__ import annotations

EXAMPLE_BASE_URL = "https://api.didww.com/v3"
SANDBOX_BASE_URL = "https://sandbox-api.didww.com/v3"

AUTH_API_KEY = "api_key"
# VERIFIED Getting Started: the key is sent in the `Api-Key` header.
API_KEY_HEADER = "Api-Key"
ACCEPT = "application/vnd.api+json"
CONTENT_TYPE = "application/vnd.api+json"
API_VERSION_HEADER = "X-Didww-Api-Version"
API_VERSION = "2026-04-16"

# VERIFIED Getting Started: 20 requests per second per API key, then HTTP 429.
MAX_RPS = 20
REQUEST_GAP_SECONDS = 0.12
RETRY_ON_STATUS = (429, 502, 503, 504)
RATE_LIMIT_RETRY_ROUNDS = 3
RATE_LIMIT_FALLBACK_SECONDS = 2.0
RATE_LIMIT_MAX_WAIT_SECONDS = 30.0

PATH_COUNTRIES = "/countries"
PATH_REGIONS = "/regions"
PATH_CITIES = "/cities"
PATH_DID_GROUP_TYPES = "/did_group_types"
PATH_DID_GROUPS = "/did_groups"
PATH_AVAILABLE_DIDS = "/available_dids"

# VERIFIED Get Cities: default and max page size 1000
CITIES_PAGE_SIZE = 1000
# VERIFIED pagination spec: default 50, max 100 unless overridden
MAX_PAGE_SIZE = 100
DID_GROUPS_PAGE_SIZE = 100
TYPES_PAGE_SIZE = 100
MAX_PAGE_NUMBER = 5000

# VERIFIED Get Countries / Get Regions: "Pagination is disabled"
UNPAGINATED_PATHS = (PATH_COUNTRIES, PATH_REGIONS)

# VERIFIED includes tables
DID_GROUPS_INCLUDE = "country,region,city,did_group_type,stock_keeping_units"
REGIONS_INCLUDE = "country"
CITIES_INCLUDE = "country,region"
AVAILABLE_DIDS_INCLUDE = "did_group,did_group.stock_keeping_units"

# VERIFIED sorting tables. Stable server-side order keeps pages from drifting.
SORT_BY_NAME = "name"
SORT_DID_GROUPS = "prefix"

# VERIFIED filters
FILTER_IN_STOCK = "filter[is_available]"
FILTER_COUNTRY_ID = "filter[country.id]"
FILTER_AVAILABLE_DID_GROUP = "filter[did_group.id]"
FILTER_AVAILABLE_NUMBER = "filter[number_contains]"

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
    "pagination": "https://doc.didww.com/api3/specification/pagination.html",
    "countries": "https://doc.didww.com/api3/2026-04-16/coverage-resources/countries/get-countries.html",
    "regions": "https://doc.didww.com/api3/2026-04-16/coverage-resources/regions/get-regions.html",
    "cities": "https://doc.didww.com/api3/2026-04-16/coverage-resources/city/get-cities.html",
    "did_groups": "https://doc.didww.com/api3/2026-04-16/coverage-resources/did-group/get-did-groups.html",
    "did_group_object": "https://doc.didww.com/api3/2026-04-16/coverage-resources/did-group/did-group-object.html",
    "sku": "https://doc.didww.com/api3/2026-04-16/common-definitions/stock-keeping-unit-object.html",
    "available_dids": "https://doc.didww.com/api3/2026-04-16/coverage-resources/available-did/get-available-dids.html",
}

# Top-level meta of a collection response drives pagination completeness.
META_TOTAL_RECORDS = "total_records"
# `/available_dids` reports its size as total_count instead.
META_TOTAL_COUNT = "total_count"
META_AVAILABLE_COUNT = "available_count"

# DID Group Object attributes
ATTR_PREFIX = "prefix"
ATTR_AREA_NAME = "area_name"
ATTR_FEATURES = "features"
ATTR_IS_METERED = "is_metered"
ATTR_ALLOW_ADDITIONAL_CHANNELS = "allow_additional_channels"
ATTR_SERVICE_RESTRICTIONS = "service_restrictions"

# DID Group Object meta attributes (not available through includes)
META_IS_AVAILABLE = "is_available"
META_STOCK_COUNT = "total_count"
META_AVAILABLE_DIDS_ENABLED = "available_dids_enabled"
META_NEEDS_REGISTRATION = "needs_registration"

# Stock Keeping Unit Object attributes
SKU_SETUP_PRICE = "setup_price"
SKU_MONTHLY_PRICE = "monthly_price"
SKU_CHANNELS_INCLUDED = "channels_included_count"

# Relationship names
REL_COUNTRY = "country"
REL_REGION = "region"
REL_CITY = "city"
REL_DID_GROUP_TYPE = "did_group_type"
REL_SKUS = "stock_keeping_units"
REL_DID_GROUP = "did_group"

ATTR_NAME = "name"
ATTR_ISO = "iso"
ATTR_NUMBER = "number"
