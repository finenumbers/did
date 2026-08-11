# UIS Data API contract (documentation-derived)

Nav: [`uis/SOURCE.md`](uis/SOURCE.md) · [`uis-field-mapping.md`](uis-field-mapping.md) · [`uis-implementation-notes.md`](uis-implementation-notes.md) · code `backend/app/providers/uis/contract.py`

Sources: [`uis/SOURCE.md`](uis/SOURCE.md) and HTML under [`uis/raw/`](uis/raw/).

## Transport — VERIFIED

- Protocol: JSON-RPC **2.0**
- HTTP: **POST** only
- `Content-Type`: `application/json; charset=UTF-8`
- Response: JSON UTF-8
- Snake_case names for methods and fields

## Base URL — VERIFIED

Template: `https://<hostname>/<version>`

- Host for UIS portal: `dataapi.uiscom.ru` (not `dataapi.comagic.ru` — credentials are not interchangeable)
- Current Data API version in conventions: **`v2.0`**
- Default sync base: `https://dataapi.uiscom.ru/v2.0`

## Auth — VERIFIED

### Permanent / temporary key (ЛК)

Keys are created per user in the personal account. Permanent key has unlimited lifetime; temporary key has an end date. Passed as `access_token` in method params.

### Session via `login.user`

| | |
|---|---|
| Method | `login.user` |
| Params | `login` (string, required), `password` (string, required) |
| Result | `data.access_token`, `data.expire_at` (timestamp) |
| Session TTL | **1 hour** — re-login when expired |

### Agent `user_id`

Optional/required for agent context: `user_id` (number). Required for agent acting as a customer user. Obtain users via `get.customer_users` (not used in DID sync beyond optional stored `user_id`).

### IP allowlist — VERIFIED

By default API access is denied until the caller IP is added under ЛК security API rules. `0.0.0.0/0` allows all. Agent IP must be allowlisted on the **client** account.

## Pagination — VERIFIED

| Param | Default | Max |
|---|---|---|
| `offset` | 0 | 100_000 (product hard-fails sync if `total_items` exceeds what can be fetched in this window — no silent truncate) |
| `limit` | 1000 | 10_000 |

Metadata includes total count (see Data API «Мета-параметры» / limits).

### Product pagination rules (operational)

- Stop when `offset >= total_items`, empty page, or `offset` exceeds `MAX_OFFSET`.
- A **short page** (`len < limit`) is **not** an early stop while `total_items` is known and `offset < total_items` (UIS may return a short page before the final rows; historically caused false `UIS_PAGINATION_TRUNCATED` at N−1 of N).
- `UIS_PAGINATION_TRUNCATED` only when the sync **hit `MAX_OFFSET`** and `fetched < total_items`.
- If pagination ends on an empty page inside the window with `fetched < total_items`, treat `total_items` as a hint: log warning / `total_items_mismatch`, **do not fail** the sync.

## Methods used by DID (read-only)

### Free catalog — `get.available_virtual_numbers` — VERIFIED

- Description: list of virtual numbers **available for connection**
- Audience: Agent, Client
- Params: `access_token` (required), optional `user_id`, `limit`, `offset`, `filter`, `fields`, `sort`
- Item fields (docs table):

| Field | Type | Notes |
|---|---|---|
| `phone_number` | string | Virtual number |
| `category` | enum | usual, bronze, silver, gold |
| `location_mnemonic` | enum | Region mnemonic |
| `location_name` | string | Region name |
| `onetime_payment` | number | Connection fee |
| `monthly_charge` | number | Monthly fee |
| `min_charge` | number | Min monthly account |

### Purchased catalog — `get.virtual_numbers` — VERIFIED

- Description: list of **connected** virtual numbers
- Audience: Agent, Client
- Params: same pagination/auth shape as available
- Item fields (docs table, subset used in product):

| Field | Type | Notes |
|---|---|---|
| `id` | number | Unique VN id |
| `virtual_phone_number` | string | Virtual number |
| `redirection_phone_number` | string | Linked number (often 800) |
| `activation_date` | iso8601 | Activation |
| `status` | enum | active, waiting, cleaning, prereserved, reserved, manual_lock, limit_lock |
| `category` | enum | usual, bronze, silver, gold, platinum |
| `type` | enum | va, call_tracking, dynamic_call_tracking |
| `comment` | string | |
| `name` | string | |
| `campaigns` | array | Campaign nesting — keep in raw only |
| `scenarios` | array | Scenario nesting — keep in raw only |

### Auth helper — `login.user` — VERIFIED (not used by DID product)

Vendor supports session auth via `login.user`. DID Settings/sync use **only** the ЛК API key as `access_token`.

## Forbidden for DID sync

Any `create.*` / `update.*` / `delete.*` / `set.*` mutating virtual-number or billing methods. Not called from sync, probes, or diagnostics — only `get.*` with stored `access_token`.

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

RPC errors follow Data API error groups (`access_token_*`, `limit_exceeded`, get-verb errors).
