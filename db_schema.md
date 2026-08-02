# Database schema

## Why each table

| Table | Purpose |
|---|---|
| `providers` | Independent sources registry |
| `provider_connections` | Auth/base URL/test status |
| `system_settings` | System key/value settings |
| `sync_jobs` / `sync_job_logs` | Sync orchestration audit |
| `runexis_*_raw` / `sipout_*_raw` | Per-provider raw payloads (+ optional extracts) |
| `numbers_catalog_normalized` | Cross-provider UI catalog + verification metadata |
| `number_price_history` / `number_status_history` | Conservative change tracking |

## Tradeoffs

- Separate raw tables per provider isolate schema drift.
- Polymorphic catalog link (`raw_source_table` + `raw_source_id`) avoids 8 FKs.
- All provider extracts nullable; `raw_payload` is authoritative.
- Soft-absence (`is_currently_present=false`) instead of hard-delete (no deletion semantics in provider docs).

## VERIFIED vs EXAMPLE-CONFIRMED

See `docs/providers/*-field-mapping.md`. Runexis free/purchased raw tables exist as buckets but are not populated until docs confirm endpoints.
