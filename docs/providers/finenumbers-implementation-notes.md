# Finenumbers implementation notes

## Contour A — free inventory

- Provider code: `finenumbers`.
- Unified sync mode: `free_only` (no dictionaries / purchased).
- Flow: `lookup/by-inn` pages → expand ranges → wipe `(finenumbers, free)` if `reload_allowed` → catalog insert (no raw table).
- Operator column for these rows is filled later by Contour B enrichment (same as other providers).

## Contour B — PSTN INN operator cache

- Settings UI: CRUD operators + «Загрузить кеш».
- Tables: `pstn_inn_cache_operators`, `pstn_inn_ranges_cache`.
- Refresh pulls `by-inn` ranges per enabled operator.
- Enrichment (`enrich_catalog_operators`): match MSISDN against local ranges first; missing → `lookup?phone=` with rate limit.
- Writes **only** `numbers_catalog_normalized.operator`. Never overwrites prices/geo/status from Contour B.

## Sync gate

- `require_min_cache_ready` / `is_min_cache_ready`: all three required INNs enabled with `ranges_count > 0`.
- Scheduler 21:00 Europe/Moscow skips if cache not ready or sync already running.
- Unified `POST /api/v1/sync/start` returns error if cache not ready or refresh running.
- Operator enrichment failure after successful provider cutovers → run status `partial`; catalog is not rolled back.

## Separation invariant

Do not treat Contour A free inventory as Contour B cache, and do not let Contour B wipe or rewrite inventory fields other than `operator`.
