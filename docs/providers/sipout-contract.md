# SipOut contract (documentation-derived)

Nav: [`sipout/SOURCE.md`](sipout/SOURCE.md) · [`sipout-field-mapping.md`](sipout-field-mapping.md) · [`sipout-implementation-notes.md`](sipout-implementation-notes.md) · code `backend/app/providers/sipout/contract.py`

Source: [`sipout/raw/SipOut.html`](sipout/raw/SipOut.html) only.

## Auth — VERIFIED

- Query param `key` (section «Ваш api-ключ», «Основные положения»).
- Required query params: `key`, `method`, `action`.

## Base URL — VERIFIED (example form)

`https://lk.sipout.net/userapi/?key=<key>&method=<method>&action=<action>[&params]`

## Response envelope — VERIFIED

- `result`: `ok` | `bad` (required)
- `err`: optional error code for programmers
- `err_text`: optional human-readable error
- `data`: optional payload

## POST format — VERIFIED

POST parameters must be `Multipart/form-data` when POST is used.

## DID operations — VERIFIED

`method=did`

| action | Purpose | Formal response fields |
|---|---|---|
| `free_list` | Свободные номера | `cnt`, `list` |
| `connected_list` | Список подключенных номеров → business **purchased** (product decision) | `cnt`, `list` |
| `get_cities` | Города и регионы | `cities`, `regions` |
| `connect` | Подключение (mutating — not used in sync load) | `spent_sum`, `statuses` |
| `switch_off` | Отключение (mutating — not used in sync load) | `statuses` |

### free_list GET params — VERIFIED

- `city_id` (optional)
- `mask` (optional)

Sync default: **single** call without `city_id` crawl.

## Balance (test connection) — VERIFIED

- `method=balance`, `action=get` — Текущий баланс (read-only, no params).

## EXAMPLE-CONFIRMED item keys

- free_list item: `did`, `price`, `city_id`
- connected_list item: `did`, `user_comment`, `order_id`, `doc_status`, `order_doc_required`, `doc_required`, `status`, `city_id`, `has_sms`, `sign`
- city: `id`, `name`, `eng_name`, `region_id`
- region: `id`, `name`, `capital_city`, `eng_name`, `gmt`

## Sync stages (product) — OPERATIONAL

| Stage id | Phase |
|---|---|
| `sipout_dictionaries` | cities/regions |
| `sipout_free` | free_list |
| `sipout_purchased` | connected_list |

## UNVERIFIED / limitations

- No formal item schema beyond examples.
- No currency; free `price` → catalog `period_price` (buy_price unused for SipOut free).
- No pagination documented for did list actions.
- Status string semantics (`ok`/`default`) not defined.
