# Aurora Telecom documentation source

## Free inventory (live) — regional CSVs

Host: `bill.auroratelecom.ru:8080` (BGBilling numbers export)  
Auth: **none** (public HTTP GET)  
Protocol: plain **HTTP** (not HTTPS), port **8080**

Product loads **CSV URLs configured in Settings** (`extra_settings.csv_files`).  
**`all_free.csv` is not used** and must not be fetched.

Historical regional examples (seed/backfill defaults):

| File | URL | Notes |
|---|---|---|
| Crimea.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Crimea.csv | 5 columns |
| Grozny.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Grozny.csv | 5 columns |
| MSK.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/MSK.csv | 6 columns + status → Settings flag |
| Sevastopol.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Sevastopol.csv | 5 columns |
| Simferopol.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Simferopol.csv | 5 columns |
| SPb.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/SPb.csv | 5 columns |

Directory listing is **not** used; operators edit the URL list in Settings.
## Artifacts

| File | Source |
|---|---|
| [`raw/sample.csv`](raw/sample.csv) | Short EXAMPLE-CONFIRMED snapshot (cp1251) of CSV **row shape** (not a live inventory file) |

## Observed CSV shape (row format)

| Property | Value |
|---|---|
| Header | none |
| Encoding | Windows-1251 (product also accepts valid UTF-8) |
| Delimiter | `;` |
| Columns | 5 (phone; type; fee; region; display mask) |
| Content-Type | often unset |

## Derived docs

- [`../aurora-contract.md`](../aurora-contract.md)
- [`../aurora-field-mapping.md`](../aurora-field-mapping.md)
- [`../aurora-implementation-notes.md`](../aurora-implementation-notes.md)
- Code: `backend/app/providers/aurora/contract.py`

## Rule

Live regional URLs above + sample under `aurora/raw/` are the source of truth for shape. Derived contract/mapping must not invent columns. Integration is **read-only** (GET CSV only). Fail-closed: any regional file HTTP/parse failure fails the free sync stage.
