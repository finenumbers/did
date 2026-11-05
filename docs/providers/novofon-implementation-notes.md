# Novofon implementation notes

Nav: [`novofon/SOURCE.md`](novofon/SOURCE.md) · [`novofon-contract.md`](novofon-contract.md) · [`novofon-field-mapping.md`](novofon-field-mapping.md)

## Auth settings keys

| Key | Purpose |
|---|---|
| `access_token` | Secret from the API tab. Data API token. Also the HMAC secret when `api_secret` is empty |
| `api_key` | Key from the same API tab. Required to read the order shop. Blank save does not delete it |
| `api_secret` | Optional User API HMAC secret. Blank save does not delete it. Blank value means `access_token` |
| `user_id` | Agent customer user `id` from `get.customer_users`. Blank save deletes the stored value. Ignored on a client key and never sent to the User API |

Product does **not** call `login.user`.

## Sync stages

| Stage id | Phase |
|---|---|
| `novofon_dictionaries` | skipped — no regions/cities dictionary |
| `novofon_free` | Data API connect-pool `get.available_virtual_numbers`, then User API order shop |
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
10. Empty mapped fetch must not wipe. A confirmed empty slice (`total_items=0`, catalog slice already empty, no warnings) ends that stage and does not cancel the other method. An incomplete fetch or a non-empty catalog is not wiped and does not cancel the other method either; that slice stays failed.
11. `build_city_lookup("novofon")` is empty. Do not fall through to Runexis cities.
12. PSTN min cache includes ООО «НОВОФОН-ОС» (`9703126821`). After deploy, load the cache before the next 00:00 Europe/Moscow sync. Zero ranges for this INN block every provider, not only Novofon.
13. Before number reads, classify the token once per job. `get.customer_users` with `total_items > 0` is an agent: send `user_id` only when filter `id =` finds the stored value, otherwise fail without calling number methods. Code `-32008` on that probe (live mnemonic `component_disabled`, component `dataapi_agent`) means the token is not an agent; number methods are still read without `user_id`. The same code on a number method fails that stage and keeps the server message. A client (`get.account.app_id`) is queried without `user_id`. The stored key is not removed. A confirmed zero stays successful and the stage names the account. An unclassified token is not reported as an empty warehouse.
14. Free numbers are the Data API connect-pool plus the User API shop (`https://api.novofon.com`, not `base_url`). No `api_key`, a bad payload (`numbers` missing, `status` not `success`), or any unread direction refuses the free slice with `refusal_detail` and writes nothing, including a non-empty Data API pool. Purchased still runs. `numbers: []` is an empty direction, not a failure. No Russia in the country list is an empty shop. A real zero (both sources empty, no warnings) appends `empty_suffix` to the stage text. Shop prices are stored only for currency `RUB`; `0` is kept. The stage does not raise, so a shop refusal does not skip purchased.

## Test connection

1. Require stored `access_token`.
2. Classify the key the same way as sync. An agent key without a verified `user_id` fails here and does not call the number methods.
3. For a client key, `get.virtual_numbers` and `get.available_virtual_numbers`, each with `limit=1`. An empty list is success. The message includes the account name and both `total_items`.
4. Without `api_key` the check is unsuccessful and does not call the User API. With `api_key`, one `GET /v1/direct_numbers/countries/`. Directions and numbers are not walked. A countries error fails the check even after Data API succeeded.
