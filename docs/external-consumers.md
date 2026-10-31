# Reading the catalog from another system

This is the read contract for a trusted internal caller. It does not add a partner key, a scope, or a rate limit. `/api/v1` can change with the application.

With `DID_REQUIRE_AUTH=1`, `/docs` and `/openapi.json` are off. Use this file.

## How to call

Production does not publish `did-backend:8000`. Call the existing UI host. The Next proxy forwards the caller's `Authorization` header and does not inject a token:

```http
GET https://<ui-host>/api/backend/api/v1/numbers/free?page=1&page_size=200
Authorization: Bearer <ADMIN_API_TOKEN>
```

The proxy forwards only `Authorization`, `Content-Type`, and `Accept`. Its responses do not add CORS, so this path is for a server-side caller. A browser on another origin is blocked. `BACKEND_CORS_ORIGINS` does not apply to the proxy.

`ADMIN_API_TOKEN` is set only on the backend. Do not put it on the frontend, in git, or in tickets. An empty token means machine access is off. `DID_REQUIRE_AUTH=1` still requires `ADMIN_USERNAME` and `ADMIN_PASSWORD` or the process will not start.

The token is a static admin credential. It has no expiry, no per-client identity, and no audit log. The same Bearer can start sync, wipe Twilio, replace the regions directory, and overwrite provider credentials. A leak is an admin compromise. Rotate it by changing the env and recreating the single backend replica when no sync or export is running. A restart during sync kills the worker.

Do not open `did-backend` on a public host for this contract. A separate API host is optional and discouraged.

A query-string token is not accepted. The header must be `Authorization: Bearer <token>`.

## What a read returns

Catalog lists include only rows with `is_currently_present`. Purchased rows include `client`, operator, prices, and `rtu_connected`. Treat the payload as confidential.

Pagination is offset: `page`, `page_size`, and a body of `items`, `page`, `page_size`, `total`, `total_pages`. While a sync is running, walking pages can skip or repeat a row. A consistent full extract is the unfiltered export, not a long page walk.

`filters` is a URL-encoded JSON object of string lists, for example `{"region_name":["Москва"]}`. Invalid JSON returns 400. Unknown keys and non-list values are dropped. `%` and `_` in a text search are SQL `ILIKE` wildcards and are not escaped. Pass digits for a phone search.

Unknown `sort_by` on the free and purchased lists falls back to `abc_code`. Default sort is `abc_code` / `asc`.

| Call | Page size | Search |
|---|---|---|
| `GET /api/v1/numbers/free` and `/purchased` | 1–200 | UI phone box is `number_local_q`. Also `msisdn_q`, `provider_number_key_q`, and `q` (local, msisdn, and provider key together) |
| `GET /api/v1/numbers/free/facets` and `/purchased/facets` | `limit` 1–1000 | `column` is a facet column. `msisdn` and `provider_number_key` are not facets |
| `GET /api/v1/didww/groups` and `/didww/facets` | 1–200 | `q` searches country prefix, area prefix, or their concatenation. A row is a DID group, not an E.164 number |
| `GET /api/v1/twilio/numbers` and `/twilio/facets` | 1–200 | `q` searches the phone number |
| `GET /api/v1/twilio/coverage` | 1–2000 | Country and number type, not an E.164 list |
| `GET /api/v1/mask-types` and `/mask-types/facets` | 1–200 | `mask_q` |
| `GET /api/v1/regions` | whole directory, no pages | — |

Facet columns for free and purchased numbers: `provider_code`, `abc_code`, `number_category`, `number_local`, `region_name`, `city_name`, `buy_price`, `period_price`, `mask_purchase`, `type_label`, `premium`, `operator`, `client`, `rtu_connected`.

Sortable free and purchased columns: `msisdn`, `number_local`, `abc_code`, `number_category`, `provider_number_key`, `buy_price`, `period_price`, `mask_purchase`, `region_name`, `city_name`, `type_label`, `premium`, `operator`, `client`, `rtu_connected`.

## XLSX

Direct files:

- `GET /api/v1/didww/export.xlsx`
- `GET /api/v1/twilio/export.xlsx`
- `GET /api/v1/regions/export.xlsx`
- `GET /api/v1/mask-types/export.xlsx`

Free and purchased numbers use the existing job chain. These are the only POST calls in this contract, and they only build a file:

1. `POST /api/v1/numbers/{free|purchased}/export-jobs` with JSON `sort_by`, `sort_dir`, `filters`, `number_local_q`
2. `GET /api/v1/numbers/export-jobs/{id}`
3. `GET /api/v1/numbers/export-jobs/{id}/download`

Jobs live in the memory of one backend process, disappear on restart, and expire after one hour. One filtered export runs at a time. A second returns 409 and competes with the Export button in the UI. An unfiltered export may return a ready snapshot immediately. A `ready` job includes `ticket`. Download with a matching `ticket` does not require the Bearer token. Treat the ticket as a secret.

Keep a single backend replica. Export jobs are not shared across processes.

## Errors

Unauthorized middleware responses:

```json
{"error": {"code": "UNAUTHORIZED", "message": "Требуется вход администратора", "details": {}}}
```

FastAPI `HTTPException` and query validation use `{"detail": ...}`. `GET /api/backend/health` answers without a token and only reports that the process is up. It is not catalog data and is not part of this contract.

## Do not call

The token allows these. They are not part of the read contract:

- sync, wipe, import, provider settings, test-connection, the PSTN cache, and login
- `GET /api/v1/sync/dropped.xlsx` and `GET /api/v1/sync/debug.log`
- `GET /api/v1/providers/{code}/settings` (masked secrets still expose the last four characters, and fields such as `email`, `account_sid`, `key_id`, and `numbering_login` are returned in clear text)
- `GET /api/v1/didww/available-dids` and `GET /api/v1/twilio/available-numbers` (live provider calls, not stored, they spend the provider account quota)
