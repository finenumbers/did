# Twilio — field mapping

Nav: [`twilio/SOURCE.md`](twilio/SOURCE.md) · [`twilio-contract.md`](twilio-contract.md) · [`twilio-implementation-notes.md`](twilio-implementation-notes.md)

Twilio never writes to `numbers_catalog_normalized`. Rows live in `twilio_catalog`
(one row = country + type).

## Raw tables

| API | Table | Typed columns |
|---|---|---|
| `GET AvailablePhoneNumbers.json` | `twilio_countries_raw` | `country_name`, `country_iso`, `country_beta` |
| `GET Pricing …/PhoneNumbers/Countries/{ISO}` | `twilio_pricing_raw` | `country_iso`, `price_unit` |

E.164 search results are **not** stored.

## Catalog (`twilio_catalog`)

| API source | Column | UI |
|---|---|---|
| `{country_code}:{type}` | `provider_group_key` | — |
| `country` | `country_name` | Страна |
| `country_code` | `country_iso` | ISO |
| key of `subresource_uris` | `number_type` | Тип |
| Pricing `current_price` | `period_price` | Абонплата |
| Pricing `price_unit` | `price_unit` | Валюта |
| country `beta` | `country_beta` | Beta |

Not mapped: setup/buy, region, city, prefix, capabilities, in_stock, E.164.

## Live modal (`GET /api/v1/twilio/available-numbers`)

| Twilio field | UI |
|---|---|
| `phone_number` | E.164 |
| `friendly_name` | Имя |
| `capabilities.voice/sms/mms/fax` | Voice / SMS / MMS / Fax |
| `address_requirements` | Адрес |
| `region` / `locality` | Регион / город на номере |
| `beta` | Beta номера |
