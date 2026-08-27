# Twilio — field mapping

Nav: [`twilio/SOURCE.md`](twilio/SOURCE.md) · [`twilio-contract.md`](twilio-contract.md) · [`twilio-implementation-notes.md`](twilio-implementation-notes.md)

Twilio never writes to `numbers_catalog_normalized`. Coverage lives in `twilio_catalog`
(one row = country + type). Sample E.164 rows live in `twilio_available_numbers`.

## Raw tables

| API | Table | Typed columns |
|---|---|---|
| `GET AvailablePhoneNumbers.json` | `twilio_countries_raw` | `country_name`, `country_iso`, `country_beta` |
| `GET Pricing …/PhoneNumbers/Countries/{ISO}` | `twilio_pricing_raw` | `country_iso`, `price_unit` |

Search results are persisted by «Загрузка стран» (`source=geo_sync`) and the enrichment job (`source=number_sync`). Documentation examples are never seeded.

## Catalog (`twilio_catalog`)

| API source | Column | UI (окно синхронизации) |
|---|---|---|
| `{country_code}:{type}` | `provider_group_key` | — |
| `country` | `country_name` | Страна |
| `country_code` | `country_iso` | — |
| key of `subresource_uris` | `number_type` | Тип |
| Pricing `current_price` | `period_price` | Абонплата |
| Pricing `price_unit` | `price_unit` | валюта абонплаты |
| country `beta` | `country_beta` | — |
| derived from `twilio_geo` | `region_count` / `city_count` | Регионы / Города (0 → «—») |
| COUNT of E.164 for the pair | `number_count` (API, not a column) | Номера |
| number-sync job | `numbers_synced_at` / `numbers_sync_job_id` / `numbers_sync_geo_job_id` | зелёная «Загрузка» только если geo-job id совпал |

Price is stored on the catalog row and JOINed onto numbers. It is not copied onto each E.164.

## Geo (`twilio_geo`)

Unique `(provider_id, country_iso, number_type, region_filter, locality_norm)`.

| Source | Column |
|---|---|
| search `InRegion` or empty | `region_filter` |
| AvailableNumbers `region` | `region` |
| AvailableNumbers `locality` | `locality` / `locality_norm` |

Empty locality is not a city. US/CA region count = distinct nonempty `region_filter` when present, otherwise distinct API `region`. Other countries = distinct non-empty API `region`.

## Numbers (`twilio_available_numbers`)

| API source | Column | UI |
|---|---|---|
| `phone_number` | `phone_number` | Номер |
| searched catalog country (not payload `iso_country`) | `country_iso` / `country_name` | Страна |
| searched type | `number_type` | Тип |
| `region` / `locality` | `region` / `locality` | Регион / Город |
| catalog JOIN `period_price` | — | Абонплата |
| `capabilities.voice/sms/mms/fax` | `voice` / `sms` / `mms` / `fax` | Voice / SMS / MMS / Fax |
| `address_requirements` | `address_requirements` | Адрес |
| job writer | `source` | `geo_sync` or `number_sync` |

Countries-job cutover (success only) deletes catalog, geo, and **all** numbers whose `last_sync_job_id` is not this job. Enrichment upserts live geo+numbers (`source=number_sync`) and marks the row loaded. Conflict upsert does not change a row that already belongs to another country×type. `POST /wipe` clears the Twilio tables.
