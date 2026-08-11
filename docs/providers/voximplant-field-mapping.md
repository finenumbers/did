# Voximplant → catalog field mapping

Sources: [`voximplant-contract.md`](voximplant-contract.md), raw under [`voximplant/raw/`](voximplant/raw/).

## GetNewPhoneNumbers → NormalizedNumber (free)

| API | Catalog / DTO | Marker |
|---|---|---|
| `phone_number` | `msisdn` / `provider_number_key` (normalized `7…`) | VERIFIED |
| `phone_id` | `normalized_payload.phone_id` | VERIFIED |
| `phone_installation_price` | `buy_price` | VERIFIED |
| `phone_price` | `period_price` | VERIFIED |
| `phone_category_name` | `number_type` + `number_class` | VERIFIED / EXAMPLE |
| `phone_region_name` | `region_name` / `city_name` | VERIFIED |
| request `phone_region_id` | `region_external_id` / `city_external_id` | OPERATIONAL |
| — | `status_raw=free` | OPERATIONAL |
| `phone_tax_reserve`, `phone_installation_tax_reserve` | raw / `normalized_payload` only | VERIFIED |
| `phone_country_code` | must be RU for sync rows | VERIFIED |

## GetPhoneNumberRegions → dictionaries

| API | Persist | Marker |
|---|---|---|
| `phone_region_id` | `region_external_id` (composite key with category) | VERIFIED |
| `phone_region_name` | `name` / city name | VERIFIED |
| `phone_region_code` | region_code / eng fallback | VERIFIED |
| `phone_count` | raw + slice planner | VERIFIED |
| `phone_price`, `phone_installation_price` | raw prices | VERIFIED |

## GetPhoneNumberCategories

| API | Persist | Marker |
|---|---|---|
| `phone_category_name` | `category_external_id` / name | VERIFIED |
| `can_list_phone_numbers` | filter listable | VERIFIED |
| `country_code` | must be `RU` | VERIFIED |
