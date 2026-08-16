# Finenumbers implementation notes

Nav: [`finenumbers/SOURCE.md`](finenumbers/SOURCE.md) · [`finenumbers-contract.md`](finenumbers-contract.md) · [`finenumbers-field-mapping.md`](finenumbers-field-mapping.md)

## Settings

| Key | Purpose |
|---|---|
| `auth_settings.key` | Bearer token (alias `api_key` accepted by client) |
| `base_url` | Default `https://pstn.finenumbers.com` |

## Sync stages

| Stage id | Phase |
|---|---|
| `finenumbers_free` | Contour A by-inn expand → catalog (no dictionaries stage) |
| `finenumbers_purchased` | Contour C REG → purchased + RTU flags |
| `finalize` | Dropped XLSX, inventory summary, catalog checksum |
| `operator_enrichment` | **Last** stage: Contour B fills `operator` on all present rows |

## Contour A — free inventory

- Provider code: `finenumbers`.
- Unified sync mode: `free_only` (no dictionaries / purchased).
- Flow: `lookup/by-inn` pages → expand ranges → wipe `(finenumbers, free)` if `reload_allowed` → catalog insert (no raw table).
- Operator column for these rows is filled later by Contour B enrichment (same as other providers).

## Contour B — PSTN INN operator cache

- Settings UI: CRUD operators + «Загрузить кеш».
- Tables: `pstn_inn_cache_operators`, `pstn_inn_ranges_cache`.
- Refresh pulls `by-inn` ranges per enabled operator.
- Enrichment (`enrich_catalog_operators`) runs as the **last** unified-sync stage after `finalize`.
- Every currently present free/purchased row: local ranges first; cache miss → always `lookup?phone=` (no skip for already-filled operator).
- Successful cache/API value **overwrites** existing `operator`. Empty cache+API leaves the prior value (`unresolved_kept_existing`); empty rows without operator remain coverage failures.
- Writes **only** `numbers_catalog_normalized.operator`. Never overwrites prices/geo/status from Contour B.

## Sync gate

- `require_min_cache_ready` / `is_min_cache_ready`: all `REQUIRED_OPERATORS` INNs enabled with `ranges_count > 0`.
- Scheduler 00:00 Europe/Moscow skips if cache not ready or sync already running.
- Unified `POST /api/v1/sync/start` returns error if cache not ready or refresh running.
- Operator enrichment failure after successful provider cutovers → run status `partial`; catalog is not rolled back.

## Separation invariant

Do not treat Contour A free inventory as Contour B cache, and do not let Contour B wipe or rewrite inventory fields other than `operator`.
