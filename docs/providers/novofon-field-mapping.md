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

Purchased responses have no prices. `buy_price` and `period_price` stay empty. Оператор is filled later from the PSTN INN cache (Contour B), which includes ИНН `9703126821`. Тип / Премиум / Покупка come from mask rules. Клиент and «Подключено в РТУ» come from REG when the same number is there.

## Not mapped

- No regions/cities dictionary endpoints.
- `get.available_phone_prefixes` is not inventory geography.
- Mutating VN APIs are never called.
- Numbers that do not normalize to `7XXXXXXXXXX` stay in `unmapped_raw` and the dropped XLSX.
