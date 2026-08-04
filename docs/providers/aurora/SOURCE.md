# Aurora Telecom documentation source

- Free inventory CSV (live): [all_free.csv](http://bill.auroratelecom.ru:8080/bgbilling/numbers/all_free.csv)
- Host: `bill.auroratelecom.ru:8080` (BGBilling numbers export)
- Auth: **none** (public HTTP GET)
- Protocol: plain **HTTP** (not HTTPS), port **8080**

## Artifacts

| File | Source |
|---|---|
| [`raw/sample.csv`](raw/sample.csv) | Short EXAMPLE-CONFIRMED snapshot (cp1251) cut from live export |

## Observed live shape (2026-08-04)

| Property | Value |
|---|---|
| Size | ~4.4 MB / ~52 714 rows |
| Header | none |
| Encoding | Windows-1251 |
| Delimiter | `;` |
| Columns | 5 (phone; type; fee; region; display mask) |
| Content-Type | often unset |

## Rule

Saved sample under `aurora/raw/` plus live URL is the source of truth. Derived `aurora-contract.md` / `aurora-field-mapping.md` must not invent columns. Integration is **read-only** (GET CSV only).
