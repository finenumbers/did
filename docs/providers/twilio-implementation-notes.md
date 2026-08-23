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
| Sync | `backend/app/modules/twilio/runner.py` |
| Persist | `backend/app/modules/twilio/persist.py` |

## Isolation

- `ProviderCode.twilio` is in `PROVIDER_REGISTRY`, **not** in `PROVIDER_ORDER`.
- Own stages: `countries` → `pricing` → `geo` → `cutover`.
- Own lock `TWILIO_LOCK_KEY = 88221004`.
- RU catalog sync methods return `SyncLimitation`.

## Sync flow (Загрузка регионов)

Page button only opens the viewer. `POST /api/v1/twilio/sync` starts the same `SyncJobType.twilio` job. Closing the window does not cancel it; reopen reads `GET /sync/latest`.

1. Paginate countries. Build one progress row per live `subresource_uris` type.
2. Fetch Pricing per ISO sequentially. Missing price stays empty, not 0.
3. Persist catalog upsert (no wipe yet). Geo search only for `local`:
   - non-US/CA: one GET without `Contains`; empty → no grid; non-empty → `%00%`…`%99%`.
   - US/CA: every state/province as `InRegion`, same 1+100 rule. 4xx on a state = empty, job continues.
4. Upsert `twilio_geo` + `twilio_available_numbers` (`source=geo_sync`) on every response.
5. Cutover wipe only after success: delete geo and `geo_sync` numbers whose `last_sync_job_id` is not this job. `number_sync` rows stay. Empty countries list → `EmptyTwilioFetchError`, nothing is deleted.

`job.stats.progress.summary` (`requests`, `cities_total`, `numbers_unique`) flushes at most every 2s.

## Process caveat

The job runs in a `daemon=True` thread. Uvicorn `--reload` kills it on restart. Long US geo-sync must run without reload.

## UI

- Main table: persisted E.164 sample. Caption: not a full list.
- «Загрузка регионов»: viewer with summary + country×type rows.
- «Загрузка номеров»: disabled stub (InLocality fan-out is later).
