# Finenumbers → catalog field mapping

Sources: [`finenumbers-contract.md`](finenumbers-contract.md), `backend/app/providers/finenumbers/mapper.py` (code SoT — see [`finenumbers/SOURCE.md`](finenumbers/SOURCE.md)).

## Contour A — `lookup/by-inn` range → NormalizedNumber (free)

Each PSTN range row expands to one catalog row per local number in `[rangeStart, rangeEnd]`.

| API / range field | Catalog / DTO | Marker |
|---|---|---|
| `abc` + `rangeStart`…`rangeEnd` | `msisdn` = `7{abc}{local:07d}`, `provider_number_key` | VERIFIED (code) |
| `abc` | `abc_code` | VERIFIED (code) |
| local part | `number_local` (7 digits) | VERIFIED (code) |
| `region` | `region_name` | VERIFIED (code) |
| `operator` | `operator` (may be overwritten later by Contour B enrich) | VERIFIED (code) |
| `id` | `normalized_payload.range_id` | VERIFIED (code) |
| `inn` | `normalized_payload.inn` | VERIFIED (code) |
| `capacity` | `normalized_payload.capacity` | VERIFIED (code) |
| — | `buy_price` / `period_price` = null | OPERATIONAL |
| — | `inventory_kind=free` | OPERATIONAL |
| — | no provider raw table (catalog-only persist) | OPERATIONAL |

## Contour B — operator + GAR geo enrich (not inventory)

| Source | Catalog write | Marker |
|---|---|---|
| Local `pstn_inn_ranges_cache` match on MSISDN | `operator`; if `garTerritory` present → `city_name` + `region_name` | OPERATIONAL |
| Fallback `GET /api/v1/lookup?phone=` (10-digit national) | same fields from lookup `data` | VERIFIED (code) |

`garTerritory` (Территория ГАР) is split on the first `|`: before → city, after → region. No delimiter → both fields get the cleaned value. Leading prefixes `г.о. `, `город `, `Город `, `м.р-н `, `г. ` are stripped. Empty GAR does not overwrite provider geo. PSTN `region` is not used for these columns.

Contour B **never** writes prices, status, or wipes inventory.

## Lookups

| Helper | Behavior |
|---|---|
| `phone_for_lookup(msisdn)` | Strip to 10-digit national (drop leading `7`) for Contour B API |
