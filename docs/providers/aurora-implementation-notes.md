# Aurora Telecom — implementation notes

Nav: [`aurora/SOURCE.md`](aurora/SOURCE.md) · [`aurora-contract.md`](aurora-contract.md) · [`aurora-field-mapping.md`](aurora-field-mapping.md)

## Settings

| Key | Purpose |
|---|---|
| `extra_settings.csv_files` | List of `{ url, has_status_column }`. Runtime SoT for free sync. |
| `base_url` | Unused after backfill (legacy directory mode removed). |

## Sync stages

| Stage id | Phase |
|---|---|
| `aurora_free` | Configured CSVs → free catalog (no dictionaries / purchased) |

## Operational

- **Read-only** public CSV GET; no API key.
- File list only from Settings; empty list fails sync/test.
- Startup one-shot backfill: if `csv_files` empty, derive from legacy `base_url` once (MSK flagged).
- `has_status_column`: drop status at index 1 when row has 6 fields (MSK-style).
- Cap download at 32 MB; `trust_env=False`; no redirects; host allowlisted to `bill.auroratelecom.ru`.
- Test connection streams ~64KB head of first configured file.
- Production egress: backend must reach `bill.auroratelecom.ru:8080` over **HTTP** (see `deploy/PORTAINER.md`).
- Do not commit the full live CSV; keep only `docs/providers/aurora/raw/sample.csv`.
