# Runexis field mapping

Source: `runexis/raw/Runexis.html` + `runexis-contract.md` only.

**Locked:** free/purchased inventory sync is capability-limited — do not map any endpoint into `inventory_kind=free|purchased` catalog until docs clarify.

## Category free / purchased

| provider field | where | meaning confirmed? | target | transformation | nullable? | confidence note |
|---|---|---|---|---|---|---|
| *(free inventory)* | — | no | — | DO NOT MAP | — | no free-list endpoint |
| *(purchased inventory)* | — | no | — | DO NOT MAP | — | no purchased-named endpoint |
| `number_status_id` | management query 1..10 | yes (param) | — | unclear labels | yes | TODO: VERIFY_WITH_DOC_FILE |
| `POST .../free` | «Удаление всех привязок» | yes | — | not inventory | — | |

## Regions / cities

| provider field | where | meaning confirmed? | target | transformation | nullable? | confidence note |
|---|---|---|---|---|---|---|
| `id` / `name` | regions example | example-only | region external id / name | as-is | yes | |
| `city_id` / `city_name` / `region_id` / `region_name` | cities example | example-only | city/region fields | as-is | yes | |

## Numbers shapes (NOT wired to free/purchased sync)

| provider field | where | meaning confirmed? | target if ever used | transformation | nullable? | confidence note |
|---|---|---|---|---|---|---|
| `phone_number` / `region_code` | search example | example-only | unclear MSISDN | do not concat | yes | TODO: VERIFY_WITH_DOC_FILE |
| `code` / `number` | management example | example-only | unclear MSISDN | do not concat | yes | TODO: VERIFY_WITH_DOC_FILE |
| `installationCost` | management example | example-only | candidate setup — not used in sync | — | yes | not catalogued under limitation |
| `subscriptionFee` | management example | example-only | candidate monthly — not used | — | yes | |
| `meraPrice` | management example | example-only | unclear | raw only | yes | |
| SMS | — | no | — | — | — | not found |
