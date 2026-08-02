# Runexis implementation notes

## Implemented

| Operation | Endpoint |
|---|---|
| testConnection | `GET api/v1/me` |
| sync regions | `GET api/v1/regions` |
| sync cities | `GET api/v1/regions/cities` |

Optional client helpers (not free/purchased sync): `GET api/v1/numbers`, `GET api/v1/numbers/management`, load-data upload/status.

## Not implemented as inventory sync

- free numbers — no documented free inventory endpoint → `PROVIDER_CAPABILITY_LIMITED`
- purchased numbers — same

## VERIFIED

Bearer auth; base URL; me/regions/cities paths; management `number_status_id` 1..10 without labels.

## EXAMPLE-CONFIRMED / uncertain

Region/city/number example keys; E.164 assembly; price field meanings; SMS absent.

## Live-test later

- token flow login/refresh
- pagination meta on numbers search
- clarify free/purchased mapping with provider docs update
