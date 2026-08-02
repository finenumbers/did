# SipOut field mapping

Source: `sipout/raw/SipOut.html` + `sipout-contract.md` only.

Legend — meaning confirmed?: **yes** | **example-only** | **no**

## Free numbers (`did` / `free_list`)

| provider field | where in uploaded docs | meaning confirmed? | target normalized field | transformation | nullable? | confidence note |
|---|---|---|---|---|---|---|
| `list[]` | formal response `list` | yes | raw + catalog source | iterate | n/a | formal container |
| `did` | free_list example item | example-only | `provider_number_key`, candidate `msisdn` | string as-is | yes | E.164 not formal for free item |
| `price` | free_list example item | example-only | `price_amount` only | decimal parse; no currency | yes | Locked: no setup/monthly split |
| `city_id` | example + formal GET param | yes (param) / example-only (item) | `city_external_id` | → text | yes | city name via dictionary = derived |
| *(category)* | action «Свободные номера» | yes | `inventory_kind=free` | constant | no | |
| SMS / status / region on item | — | no | — | — | — | absent on free item |

## Purchased (`did` / `connected_list`)

| provider field | where | meaning confirmed? | target | transformation | nullable? | confidence note |
|---|---|---|---|---|---|---|
| `list[]` | formal `list` | yes | raw + catalog | iterate | n/a | → `inventory_kind=purchased` (decision) |
| `did` | example | example-only | `provider_number_key` / `msisdn` | as-is | yes | |
| `status` | example | example-only | `status_raw` | as-is; no enum meaning | yes | |
| `city_id` | example | example-only | `city_external_id` | → text | yes | |
| `has_sms` | example | example-only | `has_sms` | parse 0/1 | yes | |
| setup/monthly/tariff | — | no | — | — | — | not in connected_list |

## Geo (`did` / `get_cities`)

| provider field | where | meaning confirmed? | target | transformation | nullable? | confidence note |
|---|---|---|---|---|---|---|
| `cities` / `regions` | formal | yes | raw tables | iterate | n/a | |
| `cities[].id` | example | example-only | `city_external_id` | → text | yes | |
| `cities[].name` | example | example-only | city name | as-is | yes | |
| `cities[].region_id` | example | example-only | `region_external_id` | → text | yes | |
| `regions[].id` | example | example-only | `region_external_id` | → text | yes | |
| `regions[].name` | example | example-only | region name | as-is | yes | |
