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
| DISTINCT cleaned numbers `region` / `locality` | `region_count` / `city_count` | Регионы / Города (0 → «—») |
| COUNT of E.164 for the pair | `number_count` (API, not a column) | Номера |
| number-sync job | `numbers_synced_at` / `numbers_sync_job_id` / `numbers_sync_geo_job_id` | зелёная «Загрузка» только если geo-job id совпал |

Price is stored on the catalog row and JOINed onto numbers. It is not copied onto each E.164.

## Geo (`twilio_geo`)

Unique `(provider_id, country_iso, number_type, region_filter, region_norm, locality_norm)`.

| Source | Column |
|---|---|
| search `InRegion` or empty | `region_filter` |
| classified UI region | `region` / `region_norm` |
| classified UI locality | `locality` / `locality_norm` |

`region_count` / `city_count` are `COUNT(DISTINCT)` of cleaned `twilio_available_numbers.region` / `.locality` (empty ignored). They match the numbers-table facets. `region_filter` is a US/CA search key only, not the sync «Регионы» figure.

## Numbers (`twilio_available_numbers`)

`region_raw` / `locality_raw` are the Twilio payload strings. `region` / `locality` are classified for the UI: keep-list regions only for US/CA/GB/DE/FR (US/CA codes become full names), country labels discarded, lone unknown `region` becomes a city. Other ISO: trust a distinct pair, otherwise the lone `region` is a city. Classification never invents a name that was not on that row.

| API source | Column | UI |
|---|---|---|
| `phone_number` | `phone_number` | Номер |
| searched catalog country (not payload `iso_country`) | `country_iso` / `country_name` | Страна |
| searched type | `number_type` | Тип |
| payload `region` / `locality` | `region_raw` / `locality_raw` | — |
| classified | `region` / `locality` | Регион / Город |
| catalog JOIN `period_price` | — | Абонплата |
| `capabilities.voice/sms/mms/fax` | `voice` / `sms` / `mms` / `fax` | Voice / SMS / MMS / Fax |
| `address_requirements` | `address_requirements` | Адрес |
| job writer | `source` | `geo_sync` or `number_sync` |

Countries-job cutover (success only) deletes catalog, geo, and **all** numbers whose `last_sync_job_id` is not this job. Enrichment upserts live geo+numbers (`source=number_sync`) and marks the row loaded. Conflict upsert does not change a row that already belongs to another country×type. `POST /wipe` clears the Twilio tables.
