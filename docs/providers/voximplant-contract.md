# Voximplant — machine contract

Nav: [`voximplant/SOURCE.md`](voximplant/SOURCE.md) · [`voximplant-field-mapping.md`](voximplant-field-mapping.md) · [`voximplant-implementation-notes.md`](voximplant-implementation-notes.md) · code `backend/app/providers/voximplant/contract.py`

Sources (local artifacts win — see [`voximplant/SOURCE.md`](voximplant/SOURCE.md)):
- [`voximplant/raw/Voximplant-Authorization.md`](voximplant/raw/Voximplant-Authorization.md)
- [`voximplant/raw/Voximplant-Errors.md`](voximplant/raw/Voximplant-Errors.md)
- [`voximplant/raw/Voximplant-GetAccountInfo.md`](voximplant/raw/Voximplant-GetAccountInfo.md)
- [`voximplant/raw/Voximplant-GetPhoneNumberCategories.md`](voximplant/raw/Voximplant-GetPhoneNumberCategories.md)
- [`voximplant/raw/Voximplant-GetPhoneNumberRegions.md`](voximplant/raw/Voximplant-GetPhoneNumberRegions.md)
- [`voximplant/raw/Voximplant-GetNewPhoneNumbers.md`](voximplant/raw/Voximplant-GetNewPhoneNumbers.md)

## Auth

- Control Panel → Service accounts → Generate key → `credentials.json` with `account_id`, `key_id`, `private_key`.
- Sign JWT RS256: header `{alg:RS256, typ:JWT, kid}`, payload `{iat, iss:account_id, exp<=iat+3600}`.
- Header: `Authorization: Bearer <jwt>`.
- Settings store structured `auth_settings`: `account_id`, `key_id`, `private_key` (UI accepts paste of full credentials JSON).
- Roles for listing: Owner / Admin / Accountant (`GetNewPhoneNumbers`).
- Default host: `https://api.voximplant.com`; prefer `api_address` from GetAccountInfo when present.

## HTTP

- `POST https://{host}/platform_api/{MethodName}` with **query parameters**.
- VERIFIED: responses may be HTTP 200 with `{ "error": { "code", "msg" } }` — always parse `error`.
- Relevant errors: `100` auth, `239–242` phone params, `331` no stock, `314` concurrent limit.

## Read-only boundary

Allowed:
- `GetAccountInfo` — test / currency / api_address
- `GetPhoneNumberCategories` — RU categories (`country_code=RU`, `sandbox=false`)
- `GetPhoneNumberRegions` — regions + prices (`locale=RU`)
- `GetNewPhoneNumbers` — free inventory

Never call: `AttachPhoneNumber` or other mutating phone methods. Purchased `GetPhoneNumbers` is out of scope v1.

## RU scope

- Hard filter `country_code=RU` only.
- Categories: **all** with `can_list_phone_numbers=true` (no whitelist).
- States: skip (`country_has_states=false` for RU in docs examples).

## Dictionaries

1. Categories for RU.
2. For each listable category → `GetPhoneNumberRegions` (`omit_empty` default true for stock slices; persist region rows with prices).
3. Fail dictionaries if zero listable categories or zero regions across categories.

## Free numbers (CRITICAL completeness)

Required params: `country_code`, `phone_category_name`, `phone_region_id`.
Optional: `count` (default **20** VERIFIED), `offset`, `phone_number_mask`.

Sync rules:
1. Build slices = every `(phone_category_name, phone_region_id)` with stock (`phone_count > 0`).
2. For each slice paginate `GetNewPhoneNumbers` until `offset + returned >= total_count` or empty page.
3. Slice volume truth = response `total_count`, not Regions `phone_count`.
4. If `fetched < total_count` after normal stop → fail `VOXIMPLANT_SLICE_INCOMPLETE` (no silent truncate).
5. Dedupe by normalized MSISDN (`7XXXXXXXXXX`).
6. Low concurrency (≤4) due to error `314`; retry/backoff on concurrent limit — do not skip slice.
7. `DEFAULT_PAGE_LIMIT = 20` until live probe proves a higher safe `count`.

## Sync stages (product) — OPERATIONAL

| Stage id | Phase |
|---|---|
| `voximplant_dictionaries` | Categories + Regions |
| `voximplant_free` | GetNewPhoneNumbers |

## Prices

| API field | Catalog |
|---|---|
| `phone_installation_price` | `buy_price` |
| `phone_price` | `period_price` |
| tax reserve fields | raw / payload only (do not sum in v1) |
