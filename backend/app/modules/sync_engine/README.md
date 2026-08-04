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
- Stage into UNLOGGED tables (recreated each run), then atomic wipe+cutover per `(provider, inventory_kind)` with unique-key `reload_allowed` guard
- Schedule at/after 00:00 Europe/Moscow when enabled and min PSTN INN cache is ready (`last_fired` after lock acquire; fail-closed if mark fails)
- Postgres advisory lock + unique partial index: one active sync at a time (single backend replica assumed)
- Orphan reclaim: `running` SyncRun with free advisory lock is marked failed so schedule can retry
- Unlock failure detaches the DB connection (never return a locked conn to the pool; no pool-wide unlock_all on checkin)
- Providers in unified order: SipOut, Runexis, UIS, Aurora (free only), Finenumbers
- UIS: hard-fail if `total_items` exceeds what pagination can fetch within `MAX_OFFSET` (no silent truncate)
- Known limitation: free cutover may commit before a purchased wipe-guard failure (split inventory for that provider)

## Primary entrypoints

- `POST /api/v1/sync/start` — unified only (UI + schedule)
- `GET /api/v1/sync/latest`, `/sync/runs/{id}`, `/sync/runs/{id}/logs`
