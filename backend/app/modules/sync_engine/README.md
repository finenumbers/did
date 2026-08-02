# Sync engine

## CONTRACT_BACKED

- Which provider methods run per mode (from provider contracts)
- **Real API data only:** persist exclusively live provider HTTP responses
- SipOut: dictionaries, `free_list`, `connected_list`
- Runexis: regions/cities; free via Numbering `search_numbers`; purchased via DIDAPI management
- Finenumbers: free inventory via PSTN by-inn expand; operator enrichment via cache + lookup

## OPERATIONAL

- Unified sync runs (`sync_runs`) with stage progress
- Per-provider jobs inside a run (`sync_jobs`)
- Stage into TEMP tables, then atomic wipe+cutover per `(provider, inventory_kind)` with `reload_allowed` guard
- Schedule at 21:00 Europe/Moscow when enabled and min PSTN INN cache is ready
- Postgres advisory lock + unique partial index: one active sync at a time

## Primary entrypoints

- `POST /api/v1/sync/start` — unified only (UI + schedule)
- `GET /api/v1/sync/latest`, `/sync/runs/{id}`, `/sync/runs/{id}/logs`
