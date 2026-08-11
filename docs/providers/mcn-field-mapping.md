# MCN → catalog field mapping

Sources: [`mcn-contract.md`](mcn-contract.md), [`mcn/raw/MCN-Vitrina.md`](mcn/raw/MCN-Vitrina.md).

## MappedNumberResponseDto → NormalizedNumber (free)

| API | Catalog / DTO | Marker |
|---|---|---|
| `number` / `voip_number` / `common_number_subscriber` | `msisdn` / `provider_number_key` | VERIFIED |
| `default_tariff.price_setup` | `buy_price` | VERIFIED |
| `default_tariff.price_per_period` (fallback `price`) | `period_price` | VERIFIED |
| `city_id` | `city_external_id` | VERIFIED |
| `region` (numeric id) | `region_external_id` | VERIFIED |
| city/region names from dictionaries | `city_name` / `region_name` | OPERATIONAL |
| `ndc_type_id` | `number_type` (stringified) | VERIFIED |
| `beauty_level` | `number_class` / payload | VERIFIED |
| — | `status_raw=free` | OPERATIONAL |
| `currency` | `normalized_payload.currency` | VERIFIED |

## Cities / regions dictionaries

| API | Persist |
|---|---|
| `city_id`, `city_name` | city raw |
| `region.id`, `region.name` | region link |
| `free_numbers_count` | raw + planning |
| regions list `id`, `short_name`, `code` | region raw |
