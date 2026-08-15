# Sync engine

## CONTRACT_BACKED

- Which provider methods run per mode (from provider contracts)
- **Real API data only:** persist exclusively live provider HTTP responses
- SipOut: dictionaries, `free_list`, `connected_list`
- Runexis: regions/cities; free via Numbering `search_numbers`; purchased via DIDAPI management
- UIS: free/purchased virtual numbers
- Aurora: free CSV files
- Exolve: GetList dictionaries + GetFree slices
- Voximplant: RU free slices (JWT)
- MCN: Витрина free (skipped when API key missing)
- Finenumbers: free inventory via PSTN by-inn expand; operator enrichment via cache + lookup

## OPERATIONAL

- Unified sync runs (`sync_runs`) with stage progress
- Per-provider jobs inside a run (`sync_jobs`)
- Stage into UNLOGGED tables (recreated each run), then atomic wipe+cutover per `(provider, inventory_kind)`; `reload_allowed` only blocks empty wipe (size may shrink or grow). Sync UI shows was/became via `stats.inventory_summary`.
- Schedule at/after 00:00 Europe/Moscow when enabled and min PSTN INN cache is ready (`last_fired` after lock acquire; fail-closed if mark fails). Catch-up: first claim later the same calendar day if backend was down at midnight — not a second run after `last_fired`.
- Postgres advisory lock on a **dedicated** DB session (separate from staging/work session) + unique partial index: one active sync at a time (single backend replica assumed; DB pool_size=10 / max_overflow=20 leaves API headroom while sync holds one lock connection)
- Cooperative cancel: progress writes stop if run was marked failed (orphan/reclaim); worker exits instead of overwriting aborted stages
- Orphan reclaim: `running` SyncRun with free advisory lock is marked failed (`/latest` and `/active`); age-stale for `running` also requires free lock
- Do not redeploy backend during an active sync — kills the worker and orphans the run
- Unlock failure detaches the DB connection (never return a locked conn to the pool; no pool-wide unlock_all on checkin)
- Providers in unified order: SipOut, Runexis, UIS, Aurora, Exolve, Voximplant, MCN, Finenumbers
- UIS: hard-fail if `total_items` exceeds what pagination can fetch within `MAX_OFFSET` (no silent truncate)
- Known limitation: free cutover may commit before a purchased wipe-guard failure (split inventory for that provider)
- `stats.inventory_split` / `inventory_split_providers` on the unified run when free cutover committed but purchased failed for a provider

## Primary entrypoints

- `POST /api/v1/sync/start` — unified only (UI + schedule)
- `GET /api/v1/sync/latest`, `/sync/runs/{id}`, `/sync/runs/{id}/logs`
