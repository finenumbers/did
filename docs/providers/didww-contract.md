# DIDWW — machine contract

Nav: [`didww/SOURCE.md`](didww/SOURCE.md) · [`didww-field-mapping.md`](didww-field-mapping.md) · [`didww-implementation-notes.md`](didww-implementation-notes.md) · code `backend/app/providers/didww/contract.py`

Docs: https://doc.didww.com/api3/2026-04-16/ (no vendor `raw/` in repo — see [`didww/SOURCE.md`](didww/SOURCE.md)).

## Auth

- `auth_settings.api_key` = API key from the DIDWW panel.
- Header `Api-Key: <key>` VERIFIED (Getting Started).
- `Accept` / `Content-Type`: `application/vnd.api+json` (JSON:API, no media type params) VERIFIED.
- Version header `X-Didww-Api-Version: 2026-04-16` VERIFIED.
- Default base URL `https://api.didww.com/v3`.

## Read-only boundary

Allowed (GET only):

| Method | Notes |
|---|---|
| `GET /countries` | pagination disabled; no `is_available` filter — full dictionary |
| `GET /regions?include=country` | paginated |
| `GET /cities?include=country,region` | page size default and max **1000** VERIFIED |
| `GET /did_group_types` | paginated |
| `GET /did_groups?include=country,region,city,did_group_type,stock_keeping_units&filter[is_available]=true` | page size max **100**; follow `links.next` |
| `GET /balance` | connection probe only (no currency field) |
| `GET /available_dids` | **on-demand only**, never persisted (see below) |

Never call: reservations, orders, `POST`/`PATCH`/`DELETE` on any resource, `PATCH /dids`.

## Rate limits

- 20 rps → HTTP 429 VERIFIED. Client targets ~10 rps (`REQUEST_GAP_SECONDS = 0.12`).
- Retry on 429/502/503/504 with backoff.

## Grain

One catalog row = **one DID Group** (country/region/city/prefix coverage with SKUs),
**not** an E.164 number. `did_groups` is loaded for all countries DIDWW returns —
no country is specially searched for or excluded.

## DID Group fields

Attributes (object page VERIFIED): `area_name`, `prefix`, `features[]`, `is_metered`,
`allow_additional_channels`, `service_restrictions`.

Meta (present on the **primary** resource only, not when included): `needs_registration`,
`is_available`, `available_dids_enabled`, `total_count`.

Features values (object page): `voice_in`, `voice_out`, `t38`, `sms_in`, `p2p`, `a2p`,
`emergency`, `cnam_out` — persisted as returned, no re-labelling.

## SKU (stock keeping unit)

Relationship / include name `stock_keeping_units`; JSON:API type `stock_keeping_units`.
Attributes: `setup_price`, `monthly_price` (strings), `channels_included_count`.

Display SKU rule (OPERATIONAL): prefer `channels_included_count == 0`, otherwise the
lowest `monthly_price`, then the lowest `setup_price`. All SKUs are stored in
`didww_catalog.skus_json`.

Currency is **not** returned by SKU or `/balance` — the UI shows the raw amount and
treats it as the DIDWW account currency.

## available_dids

`GET /available_dids` is optional per account, **has no pagination** and returns numbers in
random order. Vendor forbids mirroring it into another database, so it is exposed only as a
live passthrough (`GET /api/v1/didww/available-dids`) and never written to the DB.

## Isolation (OPERATIONAL)

- Own job type `sync_job_type = 'didww'`, own advisory lock, own sync button on `/didww`.
- Not in `PROVIDER_ORDER` (unified RU run) and not in `STAGE_DEFS` finalize stages.
- Empty `did_groups` response fails the job instead of wiping `didww_catalog`.
