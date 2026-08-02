# Runexis field mapping

Sources:

- Purchased / DIDAPI: `runexis/raw/Runexis.html` + `runexis-contract.md`
- Free / purchasable: `runexis/raw/Runexis-Numbering-API.docx` + `runexis-numbering-api-contract.md` (**sole** method source for free)

## Inventory categories

| category | source | filter | confidence |
|---|---|---|---|
| free | Numbering API `search_numbers` | status free (`access_state` / example `usage_statuses: ["free"]`) | VERIFIED method; filter key dual naming → live verify |
| purchased | DIDAPI `GET api/v1/numbers/management` | `status.mnemonic != "free"` | VERIFIED path title «Список номеров партнера» |

## Free numbers (Numbering API) → catalog

| provider field | where | target | transformation | nullable? | confidence |
|---|---|---|---|---|---|
| (item keys) | `search_numbers` result | raw + identity | preserve raw; map after live shape known | yes | **UNVERIFIED** — docs say «список_номеров» without full schema |
| `display_mask` | `search_numbers` | keep in raw / optional display | as-is | yes | EXAMPLE-CONFIRMED mentioned |
| `city_code` + `phone_number` | search filters / likely item | `msisdn`, `provider_number_key` | likely `"7"+city_code+phone_number` | yes | DERIVED candidate; **TODO: VERIFY_WITH_LIVE** |
| status free / `0` | filter `access_state` | inventory_kind=free | — | — | VERIFIED semantics |
| `number_type` / class 0..5 | search | status/class raw | as-is | yes | VERIFIED enum in docs |
| `ready` | meta / search | keep raw | as-is | yes | VERIFIED meaning (months / online) |
| `buy_price` | live `search_numbers` item | `buy_price` | decimal | yes | EXAMPLE-CONFIRMED live (also on `set_price` write docs) |
| `period_price` | live `search_numbers` item | `period_price` | decimal | yes | EXAMPLE-CONFIRMED live |
| `mask` | live `search_numbers` item | `mask` | as-is | yes | EXAMPLE-CONFIRMED live |
| `display_mask` | live `search_numbers` item | `display_mask` | as-is | yes | EXAMPLE-CONFIRMED live (formatted mask) |
| `book_date` | live `search_numbers` item | `book_date` | text; `0000-…` → null | yes | EXAMPLE-CONFIRMED live |
| `number_type` | live `search_numbers` item | `number_type` | as-is | yes | EXAMPLE-CONFIRMED live (0..5) |
| `points` | live `search_numbers` item | `points` | decimal | yes | EXAMPLE-CONFIRMED live |
| `date_from` | live `search_numbers` item | `date_from` | text as-is | yes | EXAMPLE-CONFIRMED live |
| `operator_fas` | live `search_numbers` item | `operator_fas` | as-is | yes | EXAMPLE-CONFIRMED live |
| `operator_id` | live `search_numbers` item | `operator_id` | as-is | yes | EXAMPLE-CONFIRMED live (often empty) |
| `last_operation_date` | live `search_numbers` item | `last_operation_date` | text as-is | yes | EXAMPLE-CONFIRMED live |
| `manager_id` | live `search_numbers` item | `manager_id` | as-is | yes | EXAMPLE-CONFIRMED live |
| `notes` | live `search_numbers` item | `notes` | as-is | yes | EXAMPLE-CONFIRMED live (often empty) |
| `abcdef` | live `search_numbers` item | `abcdef` | as-is | yes | EXAMPLE-CONFIRMED live (meaning unknown) |
| `book_price` | live `search_numbers` item | raw only | keep in raw | yes | not mapped to catalog |
| currency | — | raw only | — | yes | missing in free API; not a catalog column |
| SMS | — | raw only | — | yes | missing in free API; not a catalog column |

## Purchased numbers (DIDAPI management) → catalog

| provider field | where | target | transformation | nullable? | confidence |
|---|---|---|---|---|---|
| `id` | management | raw id / fallback key | as-is | yes | EXAMPLE-CONFIRMED |
| `code` + `number` | management | `msisdn`, `provider_number_key` | `"7"+code+number` (derived) | yes | DERIVED |
| `status.mnemonic` / `status.name` | management | `status_raw` | prefer mnemonic | yes | EXAMPLE-CONFIRMED |
| `city.id` | management nested | `city_external_id` | str | yes | EXAMPLE-CONFIRMED |
| `city.name` | management nested | `city_name` | as-is | yes | EXAMPLE-CONFIRMED |
| `tariff` | management nested | `tariff` | name/mnemonic/id label | yes | EXAMPLE-CONFIRMED live |
| `class` | management nested | `class` | name/mnemonic/id label | yes | EXAMPLE-CONFIRMED live |
| `operator` | management nested | `operator` | name/id label | yes | EXAMPLE-CONFIRMED live |
| `partner` | management nested | `partner` | name/id label | yes | EXAMPLE-CONFIRMED live |
| `project` | management nested | `project` | name/id label | yes | EXAMPLE-CONFIRMED live |
| `equipment` | management nested | `equipment` | name/id label | yes | EXAMPLE-CONFIRMED live |
| `subscriptionFee` / `subscription_fee` | management | `buy_price` (prefer) | Decimal | yes | EXAMPLE-CONFIRMED (often absent live); purchased path |
| `meraPrice` / `mera_price` | management | `buy_price` (fallback) | Decimal | yes | EXAMPLE-CONFIRMED |
| `installationCost` / `installation_cost` | management | `buy_price` (last fallback) | Decimal | yes | EXAMPLE-CONFIRMED |
| currency | — | raw only | — | yes | missing in docs; not a catalog column |
| SMS | management | raw only | — | yes | missing; not a catalog column |

## Regions / cities

| provider field | where | target | confidence |
|---|---|---|---|
| `id` / `name` | DIDAPI regions | region external id / name | EXAMPLE-CONFIRMED |
| `city_id` / `city_name` / `region_id` / `region_name` | DIDAPI cities | city/region fields | EXAMPLE-CONFIRMED |
| Numbering `get_regions` / `get_city_codes` | Numbering API | optional free-catalog dictionaries | VERIFIED methods; item schema sparse in DOCX |
