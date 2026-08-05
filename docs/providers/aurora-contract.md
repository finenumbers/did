# Aurora Telecom free CSV contract (documentation-derived)

Sources: [`aurora/SOURCE.md`](aurora/SOURCE.md) and [`aurora/raw/sample.csv`](aurora/raw/sample.csv).

## Transport — VERIFIED (live)

- Method: **GET** (one request per regional file)
- Default directory base: `http://bill.auroratelecom.ru:8080/bgbilling/numbers/`
- Fixed file list (order):
  1. `Crimea.csv`
  2. `Grozny.csv`
  3. `MSK.csv`
  4. `Sevastopol.csv`
  5. `Simferopol.csv`
  6. `SPb.csv`
- **`all_free.csv` is not part of the inventory fetch** (legacy aggregate; do not download)
- Auth: none
- Body: CSV file per URL, no JSON envelope
- Settings `base_url` (optional):
  - empty → default directory base + fixed file list
  - directory URL → that prefix + fixed file list
  - legacy single `*.csv` URL (incl. old `all_free.csv`) → **parent directory** + fixed file list (the named file itself is not fetched)
- Fail-closed: any file HTTP error / size cap / parse failure fails the whole free stage (no partial catalog cutover)
- Merge: concatenate rows; dedupe by MSISDN (first file wins)
- Each successful sync fully replaces Aurora free catalog; row count may shrink or grow vs previous run (no size-ratio wipe guard). Sync UI shows was/became counts.

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
| free_numbers | yes | Sequential GET of all regional CSVs + parse + merge |
| purchased_numbers | **no** | No purchased export in contract |
| dictionaries | **no** | No regions/cities API; geo is per-row text |
| test_connection | yes | GET head of first regional file + parse first valid 5-column row |

## Out of scope

- Write / buy / reserve endpoints
- Dynamic pagination (fixed file list only)
- Auth credentials
- Fetching `all_free.csv`
