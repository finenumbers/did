# Aurora Telecom — implementation notes

- **Read-only** public CSV GET; no API key.
- Default URL in `backend/app/providers/aurora/contract.py`; Settings may override full CSV URL via `base_url`.
- Download entire file (~4–5 MB / ~53k rows); decode UTF-8 when valid, else `cp1251`; parse with `csv` (`delimiter=';'`).
- Cap download at 32 MB; `trust_env=False` (ignore HTTP_PROXY); no redirects; host allowlisted to `bill.auroratelecom.ru`.
- Test connection streams only a ~64KB head and parses the first complete row (discards a truncated trailing line).
- Progress: download → parse rows → UNLOGGED staging wipe+cutover (same path as UIS free).
- Wipe-guard applies: empty / collapsed fetch refuses wipe of existing aurora free rows.
- Production egress: backend must reach `bill.auroratelecom.ru:8080` over **HTTP** (see `deploy/PORTAINER.md`). Vendor has no HTTPS — MITM risk is inherent to the feed.
- Do not commit the full live CSV; keep only `docs/providers/aurora/raw/sample.csv`.
