# UIS → catalog field mapping

Source methods: [`uis-contract.md`](uis-contract.md).

## Free (`get.available_virtual_numbers`)

| UIS field | Catalog / behavior |
|---|---|
| `phone_number` | Normalize to `7XXXXXXXXXX` → `msisdn`, `provider_number_key`; derive `abc_code`, `number_local`, `number_category` |
| `onetime_payment` | `buy_price` |
| `monthly_charge` | `period_price` |
| `location_name` | `region_name` |
| `location_mnemonic` | `region_external_id` (string) + raw |
| `category` | `number_type` (usual/bronze/… — beauty class, not ABC «Категория») |
| `min_charge` | raw_payload only |
| full item | `raw_payload` |

## Purchased (`get.virtual_numbers`)

| UIS field | Catalog / behavior |
|---|---|
| `virtual_phone_number` | Normalize → `msisdn`, `provider_number_key` |
| `id` | raw `external_id`; if phone missing after normalize, key `uis:{id}` |
| `status` | `status_raw` |
| `category` | `number_type` |
| `type` | raw / notes-adjacent; not ABC category |
| `name`, `comment`, `activation_date`, `redirection_phone_number` | raw_payload (+ typed raw columns where present) |
| `campaigns`, `scenarios` | raw_payload only |

## Not mapped

- Dictionaries regions/cities endpoints: none — capability unsupported.
- Mutating VN APIs: never called.
