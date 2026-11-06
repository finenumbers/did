# Novofon → catalog field mapping

Source methods: [`novofon-contract.md`](novofon-contract.md).

Catalog columns are the shared free/purchased table. Novofon does not add columns.

## Free (`get.available_virtual_numbers`)

| Novofon field | Catalog / behavior |
|---|---|
| `phone_number` | Normalize to `7XXXXXXXXXX` → `msisdn`, `provider_number_key`; derive `abc_code`, `number_local`, `number_category` (Мобильный / Городской / Бесплатный вызов) |
| `onetime_payment` | `buy_price` |
| `monthly_charge` | `period_price` |
| `location_name` | raw `location_name` only. Catalog Город/Регион come from `geographic_from_regions` (geographic ABC) and PSTN GAR (mobile / 800) |
| `location_mnemonic` | raw `location_mnemonic` only |
| `category` | raw_payload only (beauty class, not catalog «Категория») |
| `min_charge` | raw_payload only |
| full item | `raw_payload` |

## Purchased (`get.virtual_numbers`)

| Novofon field | Catalog / behavior |
|---|---|
| `virtual_phone_number` | Normalize → `msisdn`, `provider_number_key` |
| `id` | raw `external_id`. A row without a normalized phone is not inserted |
| `status` | raw `status` only (not a catalog column) |
| `category`, `type`, `activation_date`, `redirection_phone_number` | raw_payload |
| `campaigns`, `scenarios` | raw_payload only |

Data API purchased responses have no prices. `buy_price` and `period_price` stay empty on those rows. Оператор is filled later from the PSTN INN cache (Contour B), which includes ИНН `9703126821`. Тип / Премиум / Покупка come from mask rules. Клиент and «Подключено в РТУ» come from REG when the same number is there.

## Purchased cabinet (`GET /v1/direct_numbers/`)

Read only when `api_key` is set. Union with `get.virtual_numbers` on `provider_number_key`. The cabinet row supplies price and place; the Data API item is nested at `raw_payload.data_api`.

| User API field | Catalog / behavior |
|---|---|
| `number` | Russia (`country` is Russia / Россия / RU, or the label is empty and the number normalizes): `7XXXXXXXXXX` → `msisdn`, `provider_number_key`. Other countries: `{country}:{digits}`, `number_local` = digits, `abc_code` empty. Digits matching `7` + ten digits keep `msisdn` empty |
| `description` | City for a non-Russian row. Otherwise raw only |
| `country` | Region for a non-Russian row. Otherwise raw only |
| `monthly_fee` | `period_price` when `currency` is `RUB`, including `0`. `buy_price` stays empty |
| `currency` | raw only |
| `status`, `type`, `start_date` | raw `status`, `number_type`, `date_from` |
| `id` | raw `external_id` only when present. The phone is not copied into `external_id` |

## Free order shop (`GET /v1/direct_numbers/available/<DIRECTION_ID>/`)

Union with the Data API pool on `provider_number_key`. The Data API row is kept when both have the same number.

| User API field | Catalog / behavior |
|---|---|
| `numbers[].number` | Russia: `7XXXXXXXXXX` → `msisdn`, `provider_number_key`. Other countries: `{countryCodeIso}:{digits}`, `number_local` = digits. Digits matching `7` + ten digits keep `msisdn` empty |
| `numbers[].id` | `raw_payload.user_api_number_id` only |
| direction `name` | City for a non-Russian row. A Russian row leaves Город/Регион to GAR |
| country name | Region for a non-Russian row |
| `connect_fee` | `buy_price` when currency is `RUB`, including `0`. Number value wins over the direction |
| `monthly_fee` | `period_price` on the same rule |
| `currency` | raw only when it is not `RUB`; prices stay empty and the number is still stored |
| `areaCode` | raw `area_code` only |

## Not mapped

- No regions/cities dictionary endpoints.
- `get.available_phone_prefixes` is not inventory geography.
- Mutating VN APIs are never called.
- Data API numbers that do not normalize to `7XXXXXXXXXX` stay in `unmapped_raw` and the dropped XLSX. A User API row with no digits, or a Russian number that does not normalize, refuses the whole slice.
