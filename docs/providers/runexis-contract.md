# Runexis contract (documentation-derived)

Nav: [`runexis/SOURCE.md`](runexis/SOURCE.md) · [`runexis-numbering-api-contract.md`](runexis-numbering-api-contract.md) · [`runexis-field-mapping.md`](runexis-field-mapping.md) · [`runexis-implementation-notes.md`](runexis-implementation-notes.md) · code `backend/app/providers/runexis/contract.py`

Sources:

- DIDAPI REST: [`runexis/raw/Runexis.html`](runexis/raw/Runexis.html) — purchased inventory, Bearer auth, DIDAPI dictionaries.
- **Free / purchasable catalog (sole method source):** Numbering API DOCX → [`runexis-numbering-api-contract.md`](runexis-numbering-api-contract.md).

Live response shape notes marked separately.

## Base URL — VERIFIED

Introduction: `https://didapi.runexis.ru`

## Auth — VERIFIED

- Header: `Authorization: Bearer {token}` (Authenticating requests).
- Obtain tokens: `POST api/v1/login` with body `email`, `password`.
- Refresh: `POST api/v1/refresh` with body field `token` = user's **refresh_token** value.
- Login/refresh response `data` keys (EXAMPLE-CONFIRMED): `token`, `refresh_token`, `token_expire`, `refresh_token_expire`.
- Test connection: `GET api/v1/me` (requires authentication).
- No API key auth in uploaded docs.

## HTTP statuses — VERIFIED

200, 400, 401, 403, 404, 405, 500 (Introduction).

## Regions — VERIFIED paths

| Method | Path | Title |
|---|---|---|
| GET | `api/v1/regions` | Получение регионов |
| GET | `api/v1/regions/cities` | Получение городов |
| GET | `api/v1/regions/codes` | Получение кодов с регионами и городами |

## Numbers inventory — VERIFIED paths

| Method | Path | Title | Inventory role |
|---|---|---|---|
| GET | `api/v1/numbers/management` | Список номеров партнера | **Primary inventory sync source** |
| GET | `api/v1/numbers` | Поиск номеров | CRM/search of partner numbers (agreements/abonents); **not** used as free catalog |
| POST | `api/v1/numbers/book` | Бронирование номеров партнером | action only (expects 11-digit `7…`) |
| POST | `api/v1/numbers/buy` | Покупка номеров партнером | action only |
| POST | `api/v1/numbers/load-data` | Загрузка данных по номерам | CSV **upload**, not inventory fetch |
| POST | `api/v1/numbers/{number}/free` | Удаление всех привязок номера | **not** free inventory list |

### Management query — VERIFIED

Optional: `page`, `limit`, `number_status_id` (integers **1..10**), `project_id`, `tariff_id`, `city_ids[]`, `region_codes`, `class_id[]`, `operator_id`, `phone_number`, …

Pagination envelope EXAMPLE-CONFIRMED: `meta.total`, `meta.page`, `meta.limit`.

### Status split (product mapping)

| Inventory | Rule | Evidence |
|---|---|---|
| **free** (available for purchase) | **Numbering API** JSON-RPC `search_numbers` with free status filter | Sole source: `Runexis-Numbering-API.docx` / [`runexis-numbering-api-contract.md`](runexis-numbering-api-contract.md). **Not** DIDAPI `management`. |
| **purchased** | DIDAPI `GET api/v1/numbers/management`, `status.mnemonic != "free"` | Title «Список номеров партнера»; live: `allocated`, `sump`. |

### Free numbers — superseded by Numbering API

DIDAPI `GET api/v1/numbers/management?number_status_id=1` is **not** the product free/for-sale catalog. That path stays unused for free sync.

Use Numbering API only — see [`runexis-numbering-api-contract.md`](runexis-numbering-api-contract.md):

- Base: `https://did-api.runexis.ru/`
- Auth: `connect` → session id
- Catalog: `search_numbers` (+ optional `search_numbers_count`)
- Mutating methods (`reserv_numbers`, `book_numbers`, `sell_numbers`, …) — **forbidden** in this project

**What is NOT a free inventory source in DIDAPI HTML:**

| Path | Why not |
|---|---|
| `GET api/v1/numbers/management` (free mnemonic) | Partner-pool status, not Numbering marketplace |
| `POST api/v1/numbers/{number}/free` | Unbind action |
| `GET api/v1/numbers` | CRM search |
| `POST api/v1/numbers/book` / `buy` | Mutating DIDAPI actions — forbidden to call |
| `POST api/v1/numbers/load-data` | CSV upload |

## EXAMPLE-CONFIRMED management item keys

Docs example (camelCase): `id`, `code`, `number`, `status{id,name,mnemonic}`, `city{id,name}`, `tariff{id,name}`, `installationCost`, `subscriptionFee`, `meraPrice`, …

Live responses observed (snake_case variants): `ip_address`, `mera_price`, `last_action_at`; nested `status.id` as integer; price fields often absent/null.

## MSISDN assembly — DERIVED

`msisdn = "7" + code + number` when `code` and `number` are present and `number` is not already an 11-digit `7…` value.

Evidence: management `code`/`number` match search `region_code`/`phone_number`; book/buy require 11 digits starting with `7`.

## Not used for inventory sync

- `GET api/v1/numbers` — agreement/abonent search view of partner numbers
- `load-data` upload endpoints
- `POST .../free` unbind action
