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
| `GET /countries?sort=name` | "Pagination is disabled" VERIFIED — one response holds the whole dictionary. Also the connection probe. |
| `GET /regions?include=country&sort=name` | "Pagination is disabled" VERIFIED |
| `GET /cities?include=country,region&sort=name` | page size default and max **1000** VERIFIED |
| `GET /did_group_types?sort=name` | paginated (default 50, max 100) |
| `GET /did_groups?include=country,region,city,did_group_type,stock_keeping_units&filter[is_available]=true&sort=prefix` | page size max **100**; page by `meta.total_records` (see Pagination) |
| `GET /available_dids?filter[did_group.id]=…` | **on-demand only**, never persisted (see below) |

`filter[is_available]` also exists on `/countries` and `/cities`; the sync does not use it
there because the dictionaries are stored in full.

Never call: reservations, orders, `POST`/`PATCH`/`DELETE` on any resource, `PATCH /dids`.

## Pagination

- Query parameters `page[number]` / `page[size]`; default page size 50, max 100 unless the
  endpoint overrides it VERIFIED.
- Real responses expose **only `links.first` and `links.last`** — `links.next` is never
  returned (verified in the Get DID Groups, Get DID Group Types and Get Areas examples), so
  paging must not depend on it.
- Completeness comes from top-level `meta.total_records` (re-read on every page) and
  `links.last` `page[number]`. Keep requesting pages while `fetched < total_records`
  even if a page is short or all-duplicate. Stop on an empty page, `fetched >= total`,
  or `page >= last`. When meta is absent, stop on the first partial page.
- If the walk ends with `fetched < total_records`, the client raises
  `DIDWW_SLICE_INCOMPLETE` and the job fails instead of persisting a partial catalog.
  A successful walk fully replaces `didww_catalog` (not a delta).
- Every paginated collection is requested with a documented `sort` value so pages do not
  drift between requests.

## Rate limits

- 20 rps per API key → HTTP 429 VERIFIED. Client spaces requests by
  `REQUEST_GAP_SECONDS = 0.12` (~8 rps).
- Retry on 429/502/503/504 with backoff; on 429 the `Retry-After` header is honoured.

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

Currency is **not** returned by the SKU object — the UI shows the raw amount and treats it
as the DIDWW account currency. Prices are fractions of a unit (`"0.0"`, `"0.3"`, `"0.8"`),
so they are stored as `numeric(18,4)` and rendered with decimals, never rounded to whole
units like the RU catalog.

## available_dids

`GET /available_dids` is optional per account (disabled by default), **has no pagination or
sorting** and returns numbers in random order; the docs report the match size in top-level
`meta.total_count` / `meta.available_count` (hundreds of thousands account-wide). The vendor
forbids mirroring it into another database, so it is exposed only as a live passthrough
(`GET /api/v1/didww/available-dids`) that requires `filter[did_group.id]` and/or
`filter[number_contains]`, caps the returned list and never writes to the DB.

## Isolation (OPERATIONAL)

- Own job type `sync_job_type = 'didww'`, own advisory lock, own sync button on `/didww`.
- Not in `PROVIDER_ORDER` (unified RU run) and not in `STAGE_DEFS` finalize stages.
- Empty `did_groups` response fails the job instead of wiping `didww_catalog`.
