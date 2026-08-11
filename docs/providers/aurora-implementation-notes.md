# Aurora Telecom — implementation notes

Nav: [`aurora/SOURCE.md`](aurora/SOURCE.md) · [`aurora-contract.md`](aurora-contract.md) · [`aurora-field-mapping.md`](aurora-field-mapping.md)

## Settings

| Key | Purpose |
|---|---|
| `base_url` | CSV directory (or legacy full `.csv` path → parent folder). No auth. |

## Sync stages

| Stage id | Phase |
|---|---|
| `aurora_free` | Regional CSVs → free catalog (no dictionaries / purchased) |

## Operational

- **Read-only** public CSV GET; no API key.
- Default URL in `backend/app/providers/aurora/contract.py`; Settings may override via `base_url`.
- Fixed regional files (Crimea, Grozny, MSK, Sevastopol, Simferopol, SPb); `all_free.csv` not used.
- Download per file; decode UTF-8 when valid, else `cp1251`; parse with `csv` (`delimiter=';'`).
- Cap download at 32 MB; `trust_env=False` (ignore HTTP_PROXY); no redirects; host allowlisted to `bill.auroratelecom.ru`.
- Test connection streams only a ~64KB head and parses the first complete row (discards a truncated trailing line).
- Persist: staging wipe+cutover; wipe-guard on empty / collapsed fetch.
- Production egress: backend must reach `bill.auroratelecom.ru:8080` over **HTTP** (see `deploy/PORTAINER.md`). Vendor has no HTTPS — MITM risk is inherent to the feed.
- Do not commit the full live CSV; keep only `docs/providers/aurora/raw/sample.csv`.
