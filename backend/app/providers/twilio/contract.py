"""Twilio AvailablePhoneNumbers + Pricing contract — mirrors docs/providers/twilio-contract.md."""

from __future__ import annotations

EXAMPLE_BASE_URL = "https://api.twilio.com/2010-04-01"
PRICING_BASE_URL = "https://pricing.twilio.com/v1"

AUTH_ACCOUNT_SID = "account_sid"
AUTH_AUTH_TOKEN = "auth_token"

PAGE_SIZE = 1000
MAX_PAGE_SIZE = 1000
MAX_PAGES = 50
RATE_LIMIT_RETRY_ROUNDS = 3
RATE_LIMIT_FALLBACK_SECONDS = 2.0
RATE_LIMIT_MAX_WAIT_SECONDS = 30.0
REQUEST_GAP_SECONDS = 0.2
RETRY_ON_STATUS = (429, 502, 503, 504)

PATH_AVAILABLE_COUNTRIES = "/Accounts/{account_sid}/AvailablePhoneNumbers.json"
PATH_AVAILABLE_COUNTRY = "/Accounts/{account_sid}/AvailablePhoneNumbers/{country_code}.json"
PATH_AVAILABLE_TYPE = (
    "/Accounts/{account_sid}/AvailablePhoneNumbers/{country_code}/{type_path}"
)
PATH_PRICING_COUNTRY = "/PhoneNumbers/Countries/{country_code}"

# Official HTML docs describe Local / TollFree / Mobile. OpenAPI/SDK also expose
# National, Voip, SharedCost, MachineToMachine. Catalog rows are created only when
# the live country `subresource_uris` contains the key.
SEARCH_TYPE_PATHS: dict[str, str] = {
    "local": "Local.json",
    "mobile": "Mobile.json",
    "toll_free": "TollFree.json",
    "voip": "Voip.json",
    "national": "National.json",
    "shared_cost": "SharedCost.json",
    "machine_to_machine": "MachineToMachine.json",
}

# Pricing v1 number_type values. Missing keys (voip, shared_cost, m2m) stay unpriced.
PRICING_TYPE_MAP: dict[str, str] = {
    "local": "local",
    "mobile": "mobile",
    "national": "national",
    "toll_free": "toll free",
}

COUNTRIES_KEY = "countries"
AVAILABLE_NUMBERS_KEY = "available_phone_numbers"
SUBRESOURCE_URIS = "subresource_uris"

DOC_REFS = {
    "phone_numbers_api": "https://www.twilio.com/docs/phone-numbers/api",
    "available": "https://www.twilio.com/docs/phone-numbers/api/availablephonenumber-resource",
    "local": "https://www.twilio.com/docs/phone-numbers/api/availablephonenumberlocal-resource",
    "toll_free": "https://www.twilio.com/docs/phone-numbers/api/availablephonenumber-tollfree-resource",
    "mobile": "https://www.twilio.com/docs/phone-numbers/api/availablephonenumber-mobile-resource",
    "pricing": "https://www.twilio.com/docs/phone-numbers/pricing",
}
