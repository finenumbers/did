# Aurora Telecom free CSV contract (documentation-derived)

Sources: [`aurora/SOURCE.md`](aurora/SOURCE.md) and [`aurora/raw/sample.csv`](aurora/raw/sample.csv).

## Transport — VERIFIED (live)

- Method: **GET**
- URL (default): `http://bill.auroratelecom.ru:8080/bgbilling/numbers/all_free.csv`
- Auth: none
- Body: CSV file, no JSON envelope
- Overridable via provider Settings `base_url` (full CSV URL)

## Encoding / CSV shape — VERIFIED (live)

| Property | Value |
|---|---|
| Encoding | Live export is typically `cp1251`. Product decode order: try `utf-8-sig` first (valid UTF-8 wins), else `cp1251` |
| Delimiter | `;` |
| Header row | **none** |
| Quoting | RFC-ish CSV; column 1 typically quoted (`"+7 (…)"`) |
| Column count | **5** per row |

## Columns — VERIFIED (live)

| Index | Meaning | Example |
|---|---|---|
| 0 | Phone (display-formatted) | `+7 (3652) 777007` |
| 1 | Beauty / tariff type | `ПЛАТИНОВЫЙ`, `ПРОСТОЙ`, … |
| 2 | Period fee text | `75990 Руб.` or `ДОГОВОРНАЯ` |
| 3 | Geo text | `г. Симферополь\|Республика Крым` or `г. Москва` or `Российская Федерация` |
| 4 | Display mask description | `[ AAA-XXX - 3 одинаковых в начале ] …` |

## Capabilities

| Capability | Supported | Notes |
|---|---|---|
| free_numbers | yes | Full CSV download + parse |
| purchased_numbers | **no** | No purchased export in contract |
| dictionaries | **no** | No regions/cities API; geo is per-row text |
| test_connection | yes | GET + parse first valid 5-column row |

## Out of scope

- Write / buy / reserve endpoints
- Pagination (single file)
- Auth credentials
