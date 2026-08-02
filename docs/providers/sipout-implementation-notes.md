# SipOut implementation notes

## Implemented actions

| Action | Use |
|---|---|
| `balance` / `get` | testConnection |
| `did` / `get_cities` | sync regions + cities (one call) |
| `did` / `free_list` | sync free numbers (single call, no city crawl) |
| `did` / `connected_list` | sync purchased numbers |

## VERIFIED fields

Envelope `result`/`err`/`err_text`/`data`; formal `cnt`/`list`; formal `cities`/`regions`; GET `city_id`/`mask` on free_list.

## EXAMPLE-CONFIRMED only

Item keys for free/connected/geo — mapped optionally with `example_confirmed` markers; free `price` → `period_price`.

## Live-test later

- free_list without city_id coverage
- stability of example item keys
- has_sms encoding
- status string meanings
