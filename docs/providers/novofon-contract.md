# Novofon Data API contract (documentation-derived)

Nav: [`novofon/SOURCE.md`](novofon/SOURCE.md) · [`novofon-field-mapping.md`](novofon-field-mapping.md) · [`novofon-implementation-notes.md`](novofon-implementation-notes.md) · code `backend/app/providers/novofon/contract.py`

Sources: HTML under [`novofon/raw/`](novofon/raw/).

## Transport — VERIFIED

- Protocol: JSON-RPC **2.0**
- HTTP: **POST** only
- `Content-Type`: `application/json; charset=UTF-8`
- Response: JSON UTF-8
- Snake_case names for methods and fields
- Batch operations and notifications are not supported

## Base URL — VERIFIED

Template: `https://<hostname>/<version>`

- Host: `dataapi-jsonrpc.novofon.ru` (not UIS `dataapi.uiscom.ru` — credentials are not interchangeable)
- Current Data API version in conventions: **`v2.0`**
- Default sync base: `https://dataapi-jsonrpc.novofon.ru/v2.0`

## Auth — VERIFIED

### Permanent / temporary key (ЛК)

Keys are created per user in the personal account (Телефония → Пользователи АТС → Администратор → API). Permanent key has unlimited lifetime; temporary key has an end date. Passed as `access_token` in method params.

Product stores the key and does **not** call `login.user`. A temporary key that expires mid-sync fails the stage (`access_token_expired`); there is no password refresh.

### Session via `login.user` — VERIFIED, unused

| | |
|---|---|
| Method | `login.user` |
| Params | `login`, `password` |
| Result table | `access_token`, `expire_at`, `app_id` |
| Result example | field is `expire`, not `expire_at` |
| Session TTL | **1 hour** |

### Agent `user_id`

Optional in the settings form. A client token must be sent without `user_id` (a stored value is ignored and is not deleted). An agent token is recognized only when `get.customer_users` returns `total_items > 0`. Then `user_id` must be the `id` of a row from that method, checked with filter `id =`. The product does not pick a user automatically. An empty `get.customer_users` success is not treated as an agent.

### IP allowlist — VERIFIED

By default API access is denied until the caller IP is added under ЛК «Настройки → Правила и настройки безопасности → API». `0.0.0.0/0` allows all. Agent IP must be allowlisted on the **client** account. Error mnemonic: `ip_not_whitelisted` (`-32003`).

## Pagination — VERIFIED

| Param | Default | Max |
|---|---|---|
| `offset` | 0 | 100 000 (inclusive start index) |
| `limit` | 1000 | 10 000 |

`metadata.total_items` is the completeness counter for `get.*`. The same portal's `get.account` example uses `meta_data`; number-method examples use `metadata`. The client reads `metadata` first, then `meta_data`.

One unfiltered walk can return at most `100_000 + limit` rows. Above that, the product refetches by documented `category` filter (`=`), including `category = null`, and accepts the merge only when the concatenated row count equals the unfiltered `total_items`.

### Product page sizes (operational)

- Free `get.available_virtual_numbers`: **10 000** (flat rows).
- Purchased `get.virtual_numbers`: **1 000** (vendor default; rows nest `campaigns` / `scenarios`; HTTP read timeout is 60s).

## Methods used by DID (read-only)

### Free catalog — `get.available_virtual_numbers` — VERIFIED

- Description: virtual numbers **available for connection**
- Audience: Agent, Client
- Permission: `number_management: select` (no required component)
- Params: `access_token` (required), optional `user_id`, `limit`, `offset`, `filter`, `fields`, `sort`
- Item fields:

| Field | Type | Notes |
|---|---|---|
| `phone_number` | string | Virtual number |
| `category` | enum | `usual`, `bronze`, `silver`, `gold` |
| `location_mnemonic` | enum | Region mnemonic; allowed values are not published |
| `location_name` | string | Region name |
| `onetime_payment` | number | Connection fee |
| `monthly_charge` | number | Monthly fee |
| `min_charge` | number | Minimum monthly account |

There is no country field and no regions/cities dictionary for this method.

### Purchased catalog — `get.virtual_numbers` — VERIFIED

- Description: **connected** virtual numbers
- Audience: Agent, Client
- Permission: `number_management: select`
- Item fields:

| Field | Type | Notes |
|---|---|---|
| `id` | number | Unique VN id |
| `virtual_phone_number` | string | Virtual number |
| `redirection_phone_number` | string | Linked number, often for 800 |
| `activation_date` | iso8601 | `YYYY-MM-DD hh:mm:ss` |
| `status` | enum | `active`, `waiting`, `cleaning`, `prereserved`, `reserved`, `manual_lock`, `limit_lock` |
| `category` | enum | `usual`, `bronze`, `silver`, `gold`, `platinum` |
| `type` | enum | `va`, `call_tracking`, `dynamic_call_tracking` |
| `campaigns` | array | Nested campaigns and `site_blocks` |
| `scenarios` | array | Nested scenarios |

`is_tracking` inside `site_blocks` is EXAMPLE-CONFIRMED only. `name` and `comment` are not in the published response. No region, city, or price fields.

All statuses are stored. The catalog UI has no status column.

### Principal — VERIFIED methods, product rule

Before either number method, one classification per provider job:

1. `get.customer_users` (`limit=1`, no `user_id`). Audience: partner. `id` is the `user_id` for client methods. Non-empty `total_items` means an agent key.
2. Otherwise `get.account` (no `user_id`). Audience: client. Response example uses `meta_data` and `data[0].app_id` / `name`.
3. `forbidden` and `method_not_found` mean “not this audience”. `access_token_*` and `ip_not_whitelisted` stop classification. Both probes missing the audience, or an agent list with zero users while `get.account` is forbidden, fail the stage and do not call the number methods.
4. Agent without a matching stored `user_id`: the stage lists at most 20 users and `total_items`. No number read.
5. A confirmed empty number list is a success only after the client branch. The stage text includes the account name and `app_id`.

### Not used

| Method | Why |
|---|---|
| `enable.virtual_numbers` / `disable.virtual_numbers` | Mutating. Forbidden. |
| `logout.user` | Deletes the session key. |
| `login.user` | 1-hour session. Product uses the permanent key. |
| `get.sip_line_virtual_numbers` | Same numbers, SIP-line subset, no geography. |
| `get.campaign_available_phone_numbers` | Campaign setup, not stock. |
| `get.available_phone_prefixes` | Site-monitoring report (`prefix`, `prefix_name`). Not linked to VN methods. Example response field is `prefixe`. Not in the permissions table. |

## Limits — partial

`metadata.limits` (`day_limit`, `day_remaining`, `day_reset`, `minute_limit`, `minute_remaining`, `minute_reset`) and mnemonic `limit_exceeded` (`-32029`) are VERIFIED. The nav link «Лимиты и ограничения» has **no body** on the published index, so per-method point cost is UNVERIFIED.

On `limit_exceeded`, one retry is allowed when a minute reset of 1–120 seconds is present on the error. A day limit fails the stage before cutover.

## Response envelope — EXAMPLE-CONFIRMED

```json
{
  "jsonrpc": "2.0",
  "id": "...",
  "result": {
    "metadata": {},
    "data": [ { "...": "..." } ]
  }
}
```
