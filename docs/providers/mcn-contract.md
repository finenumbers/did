# MCN Telecom — machine contract

Sources (local artifacts win — see [`mcn/SOURCE.md`](mcn/SOURCE.md)):
- [`mcn/raw/MCN-Vitrina-openapi.json`](mcn/raw/MCN-Vitrina-openapi.json) / [`MCN-Vitrina.md`](mcn/raw/MCN-Vitrina.md)
- [`mcn/raw/MCN-token-help.md`](mcn/raw/MCN-token-help.md)

**Do not use** «Информация о номерах» (NNP) as free inventory — archived only.

## Auth

- Token from LK → Integrations → Tokens (admin on Integrations; default ★ account only).
- Settings: `auth_settings.api_key` = token string.
- OpenAPI has no `securitySchemes`. Client probes header modes on test_connection:
  1. `Authorization: Bearer <token>` (preferred)
  2. `Authorization: <token>`
  3. `X-Auth-Token: <token>`
- Persist working mode in `auth_settings.auth_header_mode` (`bearer` / `raw` / `x_auth_token`).
- Default base URL: `https://shop.mcn.ru`
- 401 = bad/missing token; 429 = rate limit → backoff/retry.

## Read-only boundary

Allowed (Витрина):
- `GET /api/protected/showcase/countries`
- `GET /api/protected/showcase/regions`
- `GET /api/protected/showcase/cities?countryCode=`
- `GET /api/protected/showcase/numbers?...`

Never call checkout/buy/mutate showcase admin APIs.

## RU scope

- Hard filter `countryCode=643` (ISO numeric RU).
- «All regions» = all RU cities from `showcase/cities` (+ regions dictionary).

## Dictionaries

1. `countries` — assert RU present.
2. `regions` — full list.
3. `cities?countryCode=643` — persist `city_id`, names, region, `free_numbers_count`.
4. Fail dictionaries if zero RU cities.

## Free numbers (CRITICAL completeness)

`GET /api/protected/showcase/numbers`

| Param | Notes |
|---|---|
| `countryCode` | required; always 643 |
| `cities` | optional city id filter (fan-out) |
| `limitPerPage` | default 25 VERIFIED; probe higher |
| `pageNumber` | default 1; 1-based |

Response: `totalNumbers`, `numbers[]`.

Sync rules:
1. Probe page size (25→100→200); use largest accepted.
2. Prefer country-wide pagination while `page * limit` covers `totalNumbers`.
3. If country-wide incomplete/unstable → fan-out cities with `free_numbers_count > 0`.
4. Per slice: fail `MCN_SLICE_INCOMPLETE` if `fetched < totalNumbers` after last page.
5. Dedupe by normalized MSISDN.
6. Concurrency ≤ 3; retry on 429/5xx.

## Prices

| API | Catalog |
|---|---|
| `default_tariff.price_setup` | `buy_price` |
| `default_tariff.price_per_period` (else `price`) | `period_price` |
| `currency` | payload meta |
