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
| Sync | `backend/app/modules/twilio/runner.py` (geo) + `numbers_runner.py` (per-row numbers) |
| Persist | `backend/app/modules/twilio/persist.py` |

## Isolation

- `ProviderCode.twilio` is in `PROVIDER_REGISTRY`, **not** in `PROVIDER_ORDER`.
- Own stages: `countries` → `pricing` → `geo` → `cutover`.
- Own lock `TWILIO_LOCK_KEY = 88221004` shared by geo and numbers jobs.
- `get_active_twilio_job` treats `SyncJobType.twilio` and `twilio_numbers` as one busy flag.
- RU catalog sync methods return `SyncLimitation`.

## Sync flow (Загрузка регионов)

Page button only opens the viewer. `POST /api/v1/twilio/sync` starts the same `SyncJobType.twilio` job. Closing the window does not cancel it; reopen reads `GET /sync/latest`.

1. Paginate countries. Build one progress row per live `subresource_uris` type.
2. Fetch Pricing per ISO sequentially. Missing price stays empty, not 0.
3. Persist catalog upsert (no wipe yet). Geo search only for `local`, in two passes:
   - First pass: every `local` country and every US/CA state/province **without** `Contains`. Empty cell → no grid later.
   - After the first pass the job knows the remaining volume (`100` per nonempty cell) and writes `requests / requests_total`.
   - Second pass: `%00%`…`%99%` only for nonempty cells. Row status: `сейчас · 78 / 100 · %78% · 4 номеров` or `сейчас · 78 / 100 · AB · %17% · 30 номеров`.
4. Upsert `twilio_geo` + `twilio_available_numbers` (`source=geo_sync`) on every response. Modal column «Номера» is unique E.164 for that country×type.
5. Cutover wipe only after success: delete geo and `geo_sync` numbers whose `last_sync_job_id` is not this job. `number_sync` rows stay. Empty countries list → `EmptyTwilioFetchError`, nothing is deleted.

`job.stats.progress.summary` (`requests`, `requests_total`, `cities_total`, `numbers_unique`) flushes at most every 2s. `requests_total` is set only after the first geo pass.

## Numbers flow (Загрузка номеров)

Page button only opens the viewer (`GET /coverage`). Start is **per catalog row**: `POST /api/v1/twilio/numbers/sync` `{country_iso, number_type}`. Poll `GET /numbers/sync/latest`. Geo running or another numbers job → 409.

1. `build_number_cells`: queryable geo = nonempty `locality` and/or `region_filter`. Empty list → one country cell (no `InRegion`/`InLocality`), including `local` with numbers but no cities.
2. Each cell of the selected row first GETs **without** `Contains`. Empty first response → skip `%00%`…`%99%` for that cell. Nonempty → run all 100 patterns. If a patterned response returns `>= 30` and the unique set for that `(cell, Contains)` grew, repeat the same GET.
3. Upsert `source=number_sync`. Conflict updates only when existing `country_iso`+`number_type` match this row (no steal).
4. After success: wipe numbers of this country×type whose `last_sync_job_id` is not this job. Then set `numbers_synced_at` / `numbers_sync_job_id` / `numbers_sync_geo_job_id=catalog.last_sync_job_id`.
5. A new geo persist clears the three number-sync fields. Green button only when `numbers_sync_geo_job_id == last_sync_job_id`.

Row status: first pass `0 / 1 / 15 / 98 · AB · 4 номеров` (no Contains); grid `78 / 1 / 15 / 98 · AB · %78% · 4 номеров` (pattern / repeat / cell index / cells). Country fallback is `1 / 1` cells.

Do not start a full US `local` run from the agent: thousands of cities × 100+ repeats.

## Process caveat

Jobs run in a `daemon=True` thread. Uvicorn `--reload` kills them on restart. Long US geo- or numbers-sync must run without reload.

## UI

- Main table: persisted E.164 sample. Caption: not a full list.
- «Загрузка регионов»: viewer with summary + country×type rows (no «Загрузка» column).
- «Загрузка номеров»: same table from DB + «Загрузка» column (red / yellow «в процессе» / green + date). Disabled until `twilio_catalog` has rows.
