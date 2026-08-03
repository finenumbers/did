# UIS Data API contract (documentation-derived)

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
| `offset` | 0 | 100_000 |
| `limit` | 1000 | 10_000 |

Metadata includes total count (see Data API «Мета-параметры» / limits).

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

### Auth helper — `login.user` — VERIFIED

Used only when permanent `access_token` is not configured.

## Forbidden for DID sync

Any `create.*` / `update.*` / `delete.*` / `set.*` mutating virtual-number or billing methods. Not called from sync, probes, or diagnostics beyond `login.user` + `get.*`.

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
