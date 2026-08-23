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
- Own stages: `countries` → `pricing` → `cutover`.
- Own lock `TWILIO_LOCK_KEY = 88221004`.
- RU catalog sync methods return `SyncLimitation`.

## Sync flow

1. Paginate countries (no search fan-out).
2. Fetch Pricing per ISO sequentially. One country miss → row without price, job continues.
3. Build rows from `subresource_uris` × Pricing. Empty countries or 0 rows → fail, no wipe.

## Live sample

`GET /api/v1/twilio/available-numbers?country=US&type=local` plus optional `in_region`, `in_locality`, `area_code`, `contains`. Never persisted. «Другие номера» rotates `Contains` `*00*`…`*99*` in the browser.
