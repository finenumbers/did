# Exolve field mapping

See also `exolve-contract.md`.

## Free NumberElement → ParsedNumberItem / NormalizedNumber

| Exolve | Field |
|---|---|
| `number_code` | `provider_number_key`, `msisdn` (via `normalize_phone`) |
| `install_fee` | `buy_price` |
| `subscription_fee` | `period_price` |
| `type_name` | `number_type` (DEF/ABC/KDU) |
| `category_name` | `number_class` (REGULAR/BRONZE/…) |
| slice `region_id` + lookup | `city_external_id` / `region_external_id` / names |
| `region_name` | fallback display name if lookup miss |
| — | `status_raw` = `free` |
| `number_options` | `raw_payload` / `normalized_payload` only |

Platform `number_category` (ABC/DEF classifier) is computed in persist — unrelated to Exolve marketing category.

## GetList regions → ParsedRegion / ParsedCity

| Exolve | Regions raw | Cities raw (leaves only) |
|---|---|---|
| `region_id` | `region_external_id` | `city_external_id` when has parent |
| `description` else `region_name` | `name` | `name` |
| `region_name` | `eng_name` | `eng_name` |
| `parent_region_id` | in raw_payload | `region_external_id` |
| parent `description` | — | `region_name` |

All regions are persisted; cities are an additional projection of leaf nodes.
