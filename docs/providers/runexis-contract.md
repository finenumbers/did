# Runexis contract (documentation-derived)

Source: [`runexis/raw/Runexis.html`](runexis/raw/Runexis.html) only.

## Base URL — VERIFIED

Introduction: `https://didapi.runexis.ru`

## Auth — VERIFIED

- Header: `Authorization: Bearer {token}` (Authenticating requests).
- Tokens via Auth `login` / `refresh`.
- Test connection: `GET api/v1/me` (requires authentication).

## HTTP statuses — VERIFIED

200, 400, 401, 403, 404, 405, 500 (Introduction).

## Regions — VERIFIED paths

| Method | Path | Title |
|---|---|---|
| GET | `api/v1/regions` | Получение регионов |
| GET | `api/v1/regions/cities` | Получение городов |
| GET | `api/v1/regions/codes` | Получение кодов с регионами и городами |

## Numbers — VERIFIED paths (relevant)

| Method | Path | Title |
|---|---|---|
| GET | `api/v1/numbers` | Поиск номеров |
| GET | `api/v1/numbers/management` | Список номеров партнера |
| POST | `api/v1/numbers/load-data` | Загрузка данных по номерам (CSV **upload**, not inventory fetch) |
| GET | `api/v1/numbers/load-data` | Список загрузок |
| GET | `api/v1/numbers/load-data/{request_id}` | Файл ошибок загрузки |
| POST | `api/v1/numbers/{number}/free` | Удаление всех привязок номера (**not** free inventory list) |

Management query: optional `page`, `limit`, `number_status_id` (integers 1..10) — **labels for ids not documented**.

## EXAMPLE-CONFIRMED response keys

- regions: `id`, `name`
- cities: `city_id`, `city_name`, `region_id`, `region_name`
- numbers search: `region_code`, `phone_number`, `region_name`, `city_id`, `city_name`, `block_status`, …
- management: `id`, `code`, `number`, `status`, `installationCost`, `subscriptionFee`, `meraPrice`, nested `city`/`tariff`, …

## Limitations — UNVERIFIED inventory mapping

- **No** documented free-numbers inventory endpoint.
- **No** documented purchased-numbers inventory endpoint.
- Therefore sync modes `free_only` / `purchased_only` / number categories in `full` are **capability limited** (product decision).
- Do not map `number_status_id` or example `status.mnemonic=free` to free inventory without further docs.
- Do not assemble E.164 from `region_code`+`phone_number` or `code`+`number` without VERIFY.
- `load-data` is upload-to-provider, not used as free/purchased fetch.
