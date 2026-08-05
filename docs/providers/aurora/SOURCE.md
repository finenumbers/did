# Aurora Telecom documentation source

## Free inventory (live) — regional CSVs

Host: `bill.auroratelecom.ru:8080` (BGBilling numbers export)  
Auth: **none** (public HTTP GET)  
Protocol: plain **HTTP** (not HTTPS), port **8080**

Product loads **six regional files** (same CSV shape).  
**`all_free.csv` is not used** and must not be fetched.

| File | URL |
|---|---|
| Crimea.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Crimea.csv |
| Grozny.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Grozny.csv |
| MSK.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/MSK.csv |
| Sevastopol.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Sevastopol.csv |
| Simferopol.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/Simferopol.csv |
| SPb.csv | http://bill.auroratelecom.ru:8080/bgbilling/numbers/SPb.csv |

Directory base (Settings optional override):  
`http://bill.auroratelecom.ru:8080/bgbilling/numbers/`

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

## Rule

Live regional URLs above + sample under `aurora/raw/` are the source of truth for shape. Derived `aurora-contract.md` / `aurora-field-mapping.md` must not invent columns. Integration is **read-only** (GET CSV only). Fail-closed: any regional file HTTP/parse failure fails the free sync stage.
