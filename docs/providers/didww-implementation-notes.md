# DIDWW — implementation notes

Nav: [`didww/SOURCE.md`](didww/SOURCE.md) · [`didww-contract.md`](didww-contract.md) · [`didww-field-mapping.md`](didww-field-mapping.md)

Operational behavior of the code, not vendor prose.

## Settings

- Settings → DIDWW: `auth_settings.api_key` + base URL (seeded `https://api.didww.com/v3`).
- «Проверить подключение» calls `GET /countries` and reports the country count.
- Missing key fails fast with `DIDWW_API_KEY_MISSING` before any HTTP request.

## Section wiring

| Piece | Location |
|---|---|
| Nav item «Нумерация DIDWW» | after «Регионы» in `frontend/src/components/layout/AppShell.tsx` |
| Page | `frontend/src/app/didww/page.tsx` + `components/didww/DidwwTable.tsx` |
| API | `backend/app/api/routes/didww.py`, prefix `/api/v1/didww` |
| Sync job | `backend/app/modules/didww/runner.py` |
| Persist | `backend/app/modules/didww/persist.py` |
| Catalog queries | `backend/app/services/didww_service.py` |

## Isolation from the RU pipeline

- `ProviderCode.didww` is registered in `PROVIDER_REGISTRY` but **not** in
  `PROVIDER_ORDER`, so the unified run and the nightly RU schedule never touch it.
- No `STAGE_DEFS` entries: DIDWW keeps its own six stages inside `SyncJob.stats.progress`
  (`countries`, `types`, `regions`, `cities`, `groups`, `cutover`).
- Own advisory lock `DIDWW_LOCK_KEY = 88221003` on `lock_engine`; the RU sync lock is
  untouched and `dispose_engine_pool()` is never called from this job.
- The «Синхронизация» page and the GAR / PSTN minimum-cache gates do not gate DIDWW.
- `sync_free_numbers` / `sync_purchased_numbers` / `sync_regions` / `sync_cities` on
  `DidwwProvider` return `SyncLimitation` — DIDWW cannot leak into the RU catalog.

## Sync flow

1. `POST /api/v1/didww/sync` creates a `sync_jobs` row with `job_type = didww`
   (409 if one is already pending/running) and spawns a background thread.
2. Stages fetch countries → did_group_types → regions → cities → did_groups
   (`filter[is_available]=true`, `include` of country/region/city/type/SKUs).
3. `persist_didww_coverage` replaces raw tables and `didww_catalog` in **one** transaction.
4. Progress and final counts are polled by the page via `GET /api/v1/didww/sync/latest`.

## Empty-fetch guard

If `did_groups` returns zero rows, the job raises `EmptyDidwwFetchError`, rolls back and
fails with the previous row count in the message. Existing catalog rows are never wiped by
an empty or failing API response, and nothing is ever seeded from documentation examples.

## Pagination

- `/countries` is requested unpaginated (vendor disables pagination there).
- `/cities` uses page size 1000, other collections 100, following `links.next` with a
  safety cap on page count.

## available_dids

Exposed only as `GET /api/v1/didww/available-dids` (live passthrough, optional filters
`did_group_id`, `number_contains`). Never stored, never called from the batch sync.
A number-picker UI on top of it is a later phase.

## Live TODOs

- `Api-Key` header spelling is locked by the live connection test (OPERATIONAL); revisit if
  DIDWW documents a different header for a newer API version.
- Currency for `setup_price` / `monthly_price` is not returned by the API; the UI shows raw
  amounts as the DIDWW account currency.
