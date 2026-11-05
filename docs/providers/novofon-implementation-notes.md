# Novofon implementation notes

Nav: [`novofon/SOURCE.md`](novofon/SOURCE.md) · [`novofon-contract.md`](novofon-contract.md) · [`novofon-field-mapping.md`](novofon-field-mapping.md)

## Auth settings keys

| Key | Purpose |
|---|---|
| `access_token` | Permanent API key from the Novofon personal account (required for sync) |
| `user_id` | Optional agent customer user id. Blank save deletes the stored value |

Product does **not** call `login.user`.

## Sync stages

| Stage id | Phase |
|---|---|
| `novofon_dictionaries` | skipped — no regions/cities dictionary |
| `novofon_free` | `get.available_virtual_numbers` |
| `novofon_purchased` | `get.virtual_numbers` |

Order in the RU run: immediately after UIS and before Finenumbers, so purchased Novofon numbers participate in REG dedup.

## Operational

1. **IP whitelist**: add the Docker host egress IP in Novofon ЛК → API security, or `0.0.0.0/0` for a lab. Same requirement as UIS, different account.
2. Host `dataapi-jsonrpc.novofon.ru` with Novofon credentials (not UIS).
3. Empty `access_token` skips the provider (the unified run stays successful). A configured token that fails still marks the run partial.
4. Page size: free 10000, purchased 1000. Requests are sequential.
5. Short page is not an early stop while `offset < total_items`. Empty page inside the window with `fetched < total_items` is `total_items_mismatch` (warning, rows kept).
6. When `total_items` exceeds `100_000 + limit`, refetch by `category` (`usual`, `bronze`, `silver`, `gold`, purchased also `platinum`, plus `= null`). Concatenated length must equal the unfiltered `total_items`. Otherwise `NOVOFON_PAGINATION_TRUNCATED` and no wipe.
7. `limit_exceeded`: one retry when minute reset is 1–120 seconds. Day limit fails the stage before cutover.
8. Blank `base_url` falls back to `https://dataapi-jsonrpc.novofon.ru/v2.0`.
9. Phone normalize: strip non-digits; `8XXXXXXXXXX` → `7…`; 10-digit national → prefix `7`. Anything else is unmapped.
10. Empty mapped fetch must not wipe.
11. `build_city_lookup("novofon")` is empty. Do not fall through to Runexis cities.
12. PSTN min cache includes ООО «НОВОФОН-ОС» (`9703126821`). After deploy, load the cache before the next 00:00 Europe/Moscow sync. Zero ranges for this INN block every provider, not only Novofon.

## Test connection

1. Require stored `access_token`.
2. `get.virtual_numbers` and `get.available_virtual_numbers`, each with `limit=1`. An empty list is success.
