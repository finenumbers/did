# Twilio — field mapping

Nav: [`twilio/SOURCE.md`](twilio/SOURCE.md) · [`twilio-contract.md`](twilio-contract.md) · [`twilio-implementation-notes.md`](twilio-implementation-notes.md)

Twilio never writes to `numbers_catalog_normalized`. Coverage lives in `twilio_catalog`
(one row = country + type). Sample E.164 rows live in `twilio_available_numbers`.

## Raw tables

| API | Table | Typed columns |
|---|---|---|
| `GET AvailablePhoneNumbers.json` | `twilio_countries_raw` | `country_name`, `country_iso`, `country_beta` |
| `GET Pricing …/PhoneNumbers/Countries/{ISO}` | `twilio_pricing_raw` | `country_iso`, `price_unit` |

Search results are persisted only by the geo-sync job (`source=geo_sync`). Documentation examples are never seeded.

## Catalog (`twilio_catalog`)

| API source | Column | UI (окно регионов) |
|---|---|---|
| `{country_code}:{type}` | `provider_group_key` | — |
| `country` | `country_name` | Страна |
| `country_code` | `country_iso` | — |
| key of `subresource_uris` | `number_type` | Тип |
| Pricing `current_price` | `period_price` | Абонплата |
| Pricing `price_unit` | `price_unit` | валюта абонплаты |
| country `beta` | `country_beta` | — |
| derived from `twilio_geo` | `region_count` / `city_count` | Регионы / Города (`local` only; 0 → «—») |

Price is stored on the catalog row and JOINed onto numbers. It is not copied onto each E.164.

## Geo (`twilio_geo`)

Unique `(provider_id, country_iso, number_type, region_filter, locality_norm)`.

| Source | Column |
|---|---|
| search `InRegion` or empty | `region_filter` |
| AvailableNumbers `region` | `region` |
| AvailableNumbers `locality` | `locality` / `locality_norm` |

Empty locality is not a city. US/CA region count = distinct `region_filter` with data. Other countries = distinct non-empty API `region`.

## Numbers (`twilio_available_numbers`)

| API source | Column | UI |
|---|---|---|
| `phone_number` | `phone_number` | Номер |
| `iso_country` / country name | `country_iso` / `country_name` | Страна |
| searched type | `number_type` | Тип |
| `region` / `locality` | `region` / `locality` | Регион / Город |
| catalog JOIN `period_price` | — | Абонплата |
| `capabilities.voice/sms/mms/fax` | `voice` / `sms` / `mms` / `fax` | Voice / SMS / MMS / Fax |
| `address_requirements` | `address_requirements` | Адрес |
| job writer | `source` | `geo_sync` or later `number_sync` |

Cutover deletes only `source=geo_sync` rows that this job did not see.
