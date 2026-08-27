# Twilio — implementation notes

Nav: [`twilio/SOURCE.md`](twilio/SOURCE.md) · [`twilio-contract.md`](twilio-contract.md) · [`twilio-field-mapping.md`](twilio-field-mapping.md)

## Settings

- Settings → Twilio: `account_sid` + `auth_token`, base URL seeded `https://api.twilio.com/2010-04-01`.
- «Проверить подключение» calls `GET AvailablePhoneNumbers.json`.
- Missing SID/token fails fast with `TWILIO_AUTH_MISSING`.

## Section wiring

| Piece | Location |
|---|---|
| Nav «Номера Twilio» | after DIDWW in `frontend/src/components/layout/AppShell.tsx` |
| Page | `frontend/src/app/twilio/page.tsx` + `components/twilio/TwilioTable.tsx` |
| API | `backend/app/api/routes/twilio.py`, prefix `/api/v1/twilio` |
| Sync | `backend/app/modules/twilio/runner.py` (countries) + `numbers_runner.py` (enrich) |
| Persist | `backend/app/modules/twilio/persist.py` |

## Isolation

- `ProviderCode.twilio` is in `PROVIDER_REGISTRY`, **not** in `PROVIDER_ORDER`.
- Own stages: `countries` → `pricing` → `sample` → `cutover`.
- Own lock `TWILIO_LOCK_KEY = 88221004` shared by countries and numbers jobs.
- `get_active_twilio_job` treats `SyncJobType.twilio` and `twilio_numbers` as one busy flag.
- If a job is `pending`/`running` but the lock is free (process restart), it is marked failed (`прервано, процесс перезапущен`) before a new start.
- RU catalog sync methods return `SyncLimitation`.

## UI

Page button **«Синхронизация»** only opens the viewer. Closing the window does not cancel a job.

Inside the window: summary, then **«Загрузка стран»**, **«Загрузка номеров»**, **«Стереть данные»**, then the coverage table (Страна | Тип | Регионы | Города | Номера | Абонплата | Загрузка | Статус).

- While a countries job is running, the table is `job.progress.rows`.
- Otherwise rows come from `GET /coverage` (page_size up to 2000) with a live overlay on the current numbers-job target.
- «Загрузка» is red until that row is enriched for the current countries snapshot (`numbers_sync_geo_job_id == last_sync_job_id`); green shows the last load date.
- «Стереть данные» asks for confirm, then `POST /wipe`.

## Загрузка стран (`POST /api/v1/twilio/sync`)

Background `SyncJobType.twilio`. Poll `GET /sync/latest`.

1. Paginate countries. One progress row per live `subresource_uris` type.
2. Fetch Pricing v1 per ISO. Missing price stays empty, not 0.
3. One `search_available` per country×type **without** `Contains` / `InRegion` / `InLocality`. Empty → «—». Non-empty → `twilio_geo` + `twilio_available_numbers` (`source=geo_sync`). No `%x%` grid.
4. Persist catalog + cutover **only after success**: upsert catalog (resets `numbers_sync_*` so all load buttons go red), then delete catalog/geo/**all** numbers whose `last_sync_job_id` is not this job.
5. Empty countries list → `EmptyTwilioFetchError`, live data unchanged. A failed run does not replace the previous catalog.

After each sample/enrich write, `finalize_coverage_geo` classifies `region`/`locality` from `region_raw`/`locality_raw` and recounts from those cleaned columns. Existing rows were classified once by alembic `0037` (`backfill_classified_geo`); GET coverage/numbers only reads. Backend serves `/health` during that upgrade so Portainer does not mark the container unhealthy. `InRegion` is still US/CA local only.

## Загрузка (row or chain)

`POST /api/v1/twilio/numbers/sync` with `{country_iso, number_type}` or `{}` for every catalog row (including already-green). Same enricher. Poll `GET /numbers/sync/latest`. Busy lock → 409.

Cells:

- US/CA `local`: each state / province (`InRegion`).
- Everything else: one country cell.

Per cell:

1. First GET **without** `Contains`. Empty → skip the cell (no `%x%`).
2. If numbers exist → write geo+numbers, then **all** `%00%`…`%99%` without skipping indexes.
3. Repeat the same `%xx%` while the page has ≥ 30 **and** fewer than two consecutive responses with no new region / city / E.164 (novelty is vs already stored facts for the row).
4. `< 30` or two empty-of-new loads → next `%x%`, not the end of the grid.

Writes go live via `ingest_available_batch` (`source=number_sync`). E.164 ownership is the catalog pair we searched (`coverage_owner`); payload `iso_country` does not change `country_iso`. Sync «Номера» counts `GROUP BY country_name, number_type` (same grain as the table filter, no join+btrim on GET). Alembic `0038` and numbers ingest realign leaked ISO by trimmed `country_name` + type. GET coverage does not write. The row is marked loaded even if every cell was empty. A row error in the chain marks that row failed and continues; auth / missing catalog fail the job.

`GET /numbers` counts without joining `twilio_catalog` unless the price facet is set. Alembic `0039` indexes `(country_name, phone_number, id)` for the default sort. The table keeps the previous page on screen until the next page 1 arrives.

## Wipe

`POST /api/v1/twilio/wipe` deletes catalog, geo, numbers, raw countries/pricing. 409 if a job actually holds the lock.

## Process caveat

Jobs run in a `daemon=True` thread. Uvicorn `--reload` or a backend restart kills them; stale recovery unblocks the next start. A full US `local` chain is long (51 probes + up to 100 patterns each). Do not start it from the agent.
