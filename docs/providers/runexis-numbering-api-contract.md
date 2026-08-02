# Runexis Numbering API contract (free / purchasable inventory)

**Sole source of truth** for Runexis numbers available for purchase (product «свободные»):  
[`runexis/raw/Runexis-Numbering-API.docx`](runexis/raw/Runexis-Numbering-API.docx)  
(text extract: [`runexis/raw/Runexis-Numbering-API.txt`](runexis/raw/Runexis-Numbering-API.txt))

DIDAPI HTML (`Runexis.html`) is **not** used for free-for-sale catalog methods.

---

## Transport — VERIFIED

| Item | Value |
|---|---|
| Protocol | JSON-RPC **2.0** |
| HTTP | **POST** |
| Base URL | `https://did-api.runexis.ru/` |
| Body | `application/x-www-form-urlencoded` |
| Form field | `jsonrpc` = JSON string of the RPC request |
| Session | returned by `connect`; duration **1 hour**, then reconnect |

Example request envelope:

```json
{
  "jsonrpc": "2.0",
  "method": "<method>",
  "params": [ ... ],
  "id": 1
}
```

---

## Auth (read session) — VERIFIED

### `connect`

```json
{
  "jsonrpc": "2.0",
  "method": "connect",
  "params": ["<login>", "<password>", "<partition>"],
  "id": 1
}
```

- Returns session id string for subsequent calls.
- Failure shape EXAMPLE-CONFIRMED: `"result": "error%"`.
- Note: docs example sometimes shows `"method": "connect "` (trailing space) — treat canonical name as `connect` (**UNVERIFIED** which form server accepts).
- Third param `partition` — documented in params list; meaning not detailed (**UNVERIFIED** whether required/optional).

### `connect_by_acces_token`

Documented; not required for password login flow.

---

## Free / purchasable inventory — VERIFIED (allowed for sync)

### Primary: `search_numbers`

```json
{
  "jsonrpc": "2.0",
  "method": "search_numbers",
  "params": [
    "<session-id>",
    { "<search-field>": "<search-pattern>" },
    "<from>",
    "<limit>"
  ],
  "id": 9
}
```

- Pagination: `from` + `limit` (offset/limit style).
- Success: `result` = list of numbers (item schema **not fully documented**).
- Documented returned field: `display_mask` (recommended pretty format) — EXAMPLE-CONFIRMED mention.

#### Status filter for free inventory

Docs field name in filter list: **`access_state`** — array of statuses.  
Allowed string values: `free`, `reserved`, `booked`, `unbooked`, `installed`, `sold`, `undefined`.

Numeric correspondence (same section):

| Code | Meaning |
|---|---|
| 0 | Свободен |
| 1 | Зарезервирован |
| 2 | Забронирован |
| 3 | Продан |
| 4 | Отрулен |
| 5 | Неопределён |
| 6 | В отстойнике |
| 7 | Открепленный |

Example in the same doc uses key **`usage_statuses`**: `["free", "sold"]` — **EXAMPLE-CONFIRMED** alternative key; which key the live server expects is **TODO: VERIFY_WITH_LIVE** (read-only). For product free sync prefer filter equivalent to status **free / 0**.

#### Other useful search fields (VERIFIED names)

`owners`, `regions`, `city_code`, `phone_number` (`?` / `*` wildcards), `city_code_near`+`phone_number_near`, `numbers`, `managers`, `operators`, `number_type` / `number_types` (0 simple … 5 bronze), `notes`, `ready` (`online` / `not-ready` / readiness date), `operator_fas`, `phone_number_mask`, `pretty`, date ranges `booked_*`, `reserved_*`, `action_*`.

City / DEF codes are **3 digits**.

#### Access control (VERIFIED)

- Without `view-all-numbers`: user sees **only free numbers** and numbers where they are responsible manager.
- Method also gated by `view-numbers`.
- Class visibility: `view-type-*` permissions.

### Count helper: `search_numbers_count`

Same search object as `search_numbers`, without `from`/`limit`. Returns count in `result`. Same visibility rules.

---

## Supporting read methods (dictionaries) — VERIFIED

| Method | Params | Use |
|---|---|---|
| `get_regions` | `[session]` | region list |
| `get_city_codes` | `[session]` | city codes list |
| `get_pretty_filters` | `[session]` | pretty-number filter ids for `pretty` search |
| `get_owners` | `[session]` | owners |
| `get_operators` | `[session]` | operators |
| `get_managers` | `[session]` | managers |

Optional analytics reads (not required for free catalog): `show_log`, `show_number_log`, `show_number_versions` (need `show-log`).

---

## Forbidden for this project (mutating) — VERIFIED titles

Do **not** call from sync, probes, or diagnostics (see project read-only rule):

`reserv_numbers`, `book_numbers`, `sell_numbers`, `install_numbers`, `return_numbers`, `buffer_numbers`, `detach_numbers`, `load_numbers_range`, `create_number`, `create_region`, `set_*`, `undefined_numbers`, tariff/discount mutators, charge creators, …

Sale workflow in docs (reserve → book → sell → install) is informational only; product must **not** execute it.

---

## Product mapping (free inventory)

| Product need | Numbering API method | Filter / notes |
|---|---|---|
| Free / available for purchase | `search_numbers` | status free (`access_state` / `usage_statuses` — verify live key) |
| Pagination | `from`, `limit` | + optional `search_numbers_count` |
| Region/code dictionaries | `get_regions`, `get_city_codes` | separate from DIDAPI `api/v1/regions*` |
| Auth for this API | `connect` | **separate** host/session from DIDAPI Bearer |

### MSISDN / identity — UNVERIFIED / DERIVED later

Docs search uses `city_code` + `phone_number` (10 digits total for install). Full E.164 `7…` assembly and exact result item keys are **not** spelled out in the DOCX → keep raw payload; derive MSISDN only after live read confirms fields (**TODO: VERIFY_WITH_LIVE**, read-only).

### Prices — PARTIAL

- Tariffs drive prices; `set_price` documents `buy_price`, `period_price`, `book_price` as **write** params.
- Whether `search_numbers` returns price fields is **not** documented → nullable mapping until live read.

### `ready` meta — VERIFIED meaning

`ready = 0` → connect immediately after pay; `ready = N` → available in N months; may still be offered for sale with disclosure.

---

## Relationship to DIDAPI (`Runexis.html`)

| Concern | Source |
|---|---|
| Free / for-sale catalog | **Numbering API only** (this contract) |
| Purchased partner numbers | DIDAPI `GET api/v1/numbers/management` (non-free) |
| DIDAPI Bearer login | DIDAPI `POST api/v1/login` |
| Numbering session | Numbering `connect` |

These are different bases (`did-api.runexis.ru` vs `didapi.runexis.ru`) and auth models.

---

## Project auth settings keys (implemented)

Stored in `provider_connections.auth_settings` (separate from DIDAPI):

| Key | Role |
|---|---|
| `numbering_login` | `connect` login |
| `numbering_password` | `connect` password |
| `numbering_partition` | optional 3rd `connect` param |
| `numbering_base_url` | override default `https://did-api.runexis.ru/` |
| `numbering_session_id` | cached session from `connect` (cleared when password changes) |

## Open questions (live)

1. Live filter key: `access_state` vs `usage_statuses` (code tries primary then fallback).
2. Exact `search_numbers` item JSON keys for msisdn/city/prices (parser flexible; raw preserved).
3. Whether `partition` is required for the account.
