# DIDWW — field mapping

Nav: [`didww/SOURCE.md`](didww/SOURCE.md) · [`didww-contract.md`](didww-contract.md) · [`didww-implementation-notes.md`](didww-implementation-notes.md)

DIDWW never writes to `numbers_catalog_normalized`. Its rows live in `didww_catalog`
(one row = one DID Group).

## Raw tables

| API collection | Table | Typed columns (beside `raw_payload`) |
|---|---|---|
| `GET /countries` | `didww_countries_raw` | `name`, `iso`, `prefix` |
| `GET /regions` | `didww_regions_raw` | `name`, `iso`, `country_external_id` |
| `GET /cities` | `didww_cities_raw` | `name`, `country_external_id`, `region_external_id` |
| `GET /did_group_types` | `didww_did_group_types_raw` | `name` |
| `GET /did_groups` | `didww_did_groups_raw` | `prefix`, `area_name`, `country_iso` |

All raw tables carry `sync_job_id`, `source_loaded_at`, `payload_hash`, `external_key`
(the JSON:API resource `id`).

## Catalog (`didww_catalog`)

| API source | Column | UI column |
|---|---|---|
| `did_groups.id` | `provider_group_key` | — (row key) |
| included `country.attributes.name` | `country_name` | Страна |
| included `country.attributes.iso` | `country_iso` | ISO |
| included `country.attributes.prefix` | `country_prefix` | Код страны |
| included `region.attributes.name` | `region_name` | Регион |
| included `city.attributes.name` (else `attributes.area_name`) | `city_name` | Город |
| `did_groups.attributes.prefix` | `area_prefix` | Префикс |
| included `did_group_type.attributes.name` | `did_type` | Тип |
| display SKU `setup_price` | `buy_price` | Покупка |
| display SKU `monthly_price` | `period_price` | Абонплата |
| display SKU `channels_included_count` | `channels_included` | Каналы |
| `did_groups.meta.total_count` | `stock_count` | В наличии |
| `did_groups.meta.available_dids_enabled` | `number_select` | Выбор номера |
| `did_groups.attributes.features[]` | `features` (comma-joined) | Возможности |
| `did_groups.meta.needs_registration` | `needs_registration` | Регистрация |
| `did_groups.attributes.is_metered` | `is_metered` | Поминутно |
| all SKUs of the group | `skus_json` | — (detail source) |

`buy_price` / `period_price` are `numeric(18,4)`: DIDWW prices are fractions of a unit
(`"0.3"`), so they are stored and rendered with decimals, never rounded to whole units.

Display SKU rule: prefer `channels_included_count == 0` (a SKU with the field absent is not
treated as zero-channel), then the lowest `monthly_price`, then the lowest `setup_price`.

Bookkeeping columns: `raw_source_id` → `didww_did_groups_raw.id`, `last_sync_job_id`,
`first_seen_at` (carried over across syncs for groups already known), `last_seen_at`,
`is_currently_present`.

## Not mapped (deliberately)

`allow_additional_channels`, `service_restrictions`, `is_available` and every other
attribute stay in `raw_payload` only — no UI column, no derived logic yet.

There is **no** ABC code, local number, PSTN operator, RTU flag or mask/type for DIDWW rows:
those belong to the RU catalog pipeline and are not applied to this section.

## Field certainty

`didww_catalog.field_verification` records certainty labels per API field
(`setup_price`, `monthly_price`, `channels_included_count`, `iso`, `is_available`,
`total_count`, `available_dids_enabled`, `needs_registration`, `stock_keeping_units`).
Labels describe field trust, not permission to seed example data — rows come only from
live API responses.
