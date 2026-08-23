# Database schema

## Why each table

| Table | Purpose |
|---|---|
| `providers` | Independent sources registry (sipout, runexis, uis, aurora, exolve, voximplant, mcn, finenumbers, didww) |
| `provider_connections` | Auth/base URL/test status |
| `system_settings` | Key/value settings (`sync_schedule`, `pstn_inn_cache_refresh`, …) |
| `sync_jobs` / `sync_job_logs` | Per-provider job audit (also used inside unified run) |
| `sync_runs` / `sync_run_logs` | Unified multi-provider sync progress + logs |
| `runexis_*_raw` / `sipout_*_raw` | Per-provider raw payloads (+ extracts) |
| `uis_free_numbers_raw` / `uis_purchased_numbers_raw` | UIS Data API free/purchased raw |
| `aurora_free_numbers_raw` | Aurora Telecom free CSV raw |
| `exolve_*_raw` | Exolve GetList/GetFree raw |
| `voximplant_*_raw` | Voximplant free/reference raw |
| `mcn_*_raw` | MCN free raw |
| `didww_*_raw` | DIDWW coverage raw (countries/regions/cities/group types/DID groups) |
| `didww_catalog` | DIDWW coverage rows (one row = one DID Group), separate from the RU catalog |
| `numbers_catalog_normalized` | Cross-provider UI catalog + verification metadata (RU providers only) |
| `number_price_history` | Reserved; unused under wipe+reload (rows deleted on wipe, sync does not append history) |
| `pstn_inn_cache_operators` | Contour B: managed INNs for operator cache |
| `pstn_inn_ranges_cache` | Contour B: by-inn ranges (enrichment reads operator only) |

## Tradeoffs

- Separate raw tables per provider isolate schema drift.
- Polymorphic catalog link (`raw_source_table` + `raw_source_id`) avoids many FKs.
- Provider extracts nullable; `raw_payload` is authoritative for raw rows.
- Production sync uses **UNLOGGED stage → atomic wipe+cutover** per inventory slice (soft-absence removed; `number_price_history` reserved unused).
- Runexis free comes from Numbering API `search_numbers`; purchased from DIDAPI `numbers/management`.
- DIDWW is coverage, not numbers: `didww_catalog` is replaced in one transaction by its own job and never joins `numbers_catalog_normalized`.

## VERIFIED vs EXAMPLE-CONFIRMED

See `docs/providers/*-field-mapping.md` and provider contracts under `backend/app/providers/*/contract.py`.
