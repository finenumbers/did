# Aurora Telecom free CSV contract (documentation-derived)

Nav: [`aurora/SOURCE.md`](aurora/SOURCE.md) · [`aurora-field-mapping.md`](aurora-field-mapping.md) · [`aurora-implementation-notes.md`](aurora-implementation-notes.md) · code `backend/app/providers/aurora/contract.py`

Sources: [`aurora/SOURCE.md`](aurora/SOURCE.md) and [`aurora/raw/sample.csv`](aurora/raw/sample.csv).

## Transport — VERIFIED (live)

- Method: **GET** (one request per configured file URL)
- Host allowlist: `bill.auroratelecom.ru` only
- File list: **only** `extra_settings.csv_files` from Settings (full URLs). No runtime `DEFAULT_CSV_FILES` / directory expansion.
- Each entry: `{ "url": "…/File.csv", "has_status_column": bool }`
- **`all_free.csv` is forbidden**
- Auth: none
- Body: CSV file per URL, no JSON envelope
- Seed / one-shot backfill may prefill the historical six regional URLs (MSK with `has_status_column: true`); after that Settings is SoT
- Fail-closed: any file HTTP error / size cap / parse failure fails the whole free stage (no partial catalog cutover)
- Merge: concatenate all mapped rows; catalog dedupe by MSISDN in sync engine (**last wins**)
- Each successful sync fully replaces Aurora free catalog

## Encoding / CSV shape — VERIFIED (live)

| Property | Value |
|---|---|
| Encoding | Live export is typically `cp1251`. Product decode order: try `utf-8-sig` first (valid UTF-8 wins), else `cp1251` |
| Delimiter | `;` |
| Header row | **none** |
| Quoting | RFC-ish CSV; column 1 typically quoted (`"+7 (…)"`) |
| Column count | **5** classic. With Settings flag `has_status_column` (MSK-style): **6** columns; status at index 1 is dropped |

## Columns — VERIFIED (live)

| Index | Meaning | Example |
|---|---|---|
| 0 | Phone (display-formatted) | `+7 (3652) 777007` |
| 1 | Beauty / tariff type (after optional status drop) | `ПЛАТИНОВЫЙ`, `ПРОСТОЙ`, … |
| 2 | Period fee text | `75990 Руб.` or `ДОГОВОРНАЯ` |
| 3 | Geo text | `г. Симферополь\|Республика Крым` or `г. Москва` or `Российская Федерация` |
| 4 | Display mask description | `[ AAA-XXX - 3 одинаковых в начале ] …` |

MSK-style 6-column layout: `phone; status; type; fee; geo; display_mask` — enabled per file via `has_status_column`.

## Capabilities

| Capability | Supported | Notes |
|---|---|---|
| free_numbers | yes | Sequential GET of configured CSVs + parse + merge |
| purchased_numbers | **no** | No purchased export in contract |
| dictionaries | **no** | No regions/cities API; geo is per-row text |
| test_connection | yes | GET head of first configured file + parse first valid row |

## Out of scope

- Write / buy / reserve endpoints
- Directory listing / auto-discovery of files on host
- Auth credentials
- Fetching `all_free.csv`
