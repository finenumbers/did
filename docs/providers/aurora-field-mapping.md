# Aurora Telecom → catalog field mapping

Source: [`aurora-contract.md`](aurora-contract.md). Inventory kind: **free** only.

| CSV column | Catalog / behavior | Confidence |
|---|---|---|
| Col0 phone | Digits → `7XXXXXXXXXX` → `msisdn`, `provider_number_key`; `abc_code` / `number_local` via msisdn split | VERIFIED live |
| Col1 type | `number_type` (UI **Тип**). When file has Settings `has_status_column` and 6 raw columns, raw col1 is status (e.g. `СВОБОДЕН`) and is **ignored**; type is then col2 | VERIFIED live |
| Col2 fee | Parse leading integer from `N Руб.` → `period_price` (UI **Абонплата**); `ДОГОВОРНАЯ` / non-numeric → `null`; original text in `raw_payload` | VERIFIED live |
| Col3 geo | See region rules → `city_name`, `region_name` | VERIFIED live |
| Col4 display mask | `display_mask` (UI **Display mask**) as-is | VERIFIED live |
| — | `buy_price`, `mask`, external geo ids | unused / null |
| full row | `raw_payload` structured dict | — |

## Region rules (col3)

1. Contains `|` → `city_name` = left trim, `region_name` = right trim
2. Else starts with `г.` or `г ` → `city_name` = full string, `region_name` = null
3. Else → `region_name` = full string, `city_name` = null

`city_external_id` / `region_external_id` = null (no external ids in CSV).

## Not mapped

- Purchased inventory: capability unsupported
- Dictionary sync: capability unsupported
