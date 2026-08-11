# Architecture

## Boundaries

```
UI (Next.js)
  → Admin API (FastAPI)
    → Unified sync + scheduler
    → Provider settings / PSTN INN cache
    → Numbers browse/export
         ↓
    SyncService (wipe+reload per provider kind)
         ↓
    provider.py → client → parser → mapper
         ↓
    raw tables → numbers_catalog_normalized
         ↓
    operator_enrichment (local INN cache → operator only, then PSTN lookup)
```

## Modules

| Area | Path | Role |
|---|---|---|
| Providers | `backend/app/providers/` | Doc-driven adapters (SipOut, Runexis, UIS, Aurora, Exolve, Voximplant, MCN, Finenumbers) |
| Sync | `backend/app/modules/sync_engine/` | Unified runs, jobs, wipe+reload, progress, schedule |
| PSTN INN cache | `backend/app/modules/pstn_inn_cache/` | Contour B: ranges cache for `catalog.operator` only |
| Settings | `provider_connections` + PSTN cache APIs | Credentials, test connection, cache refresh, schedule |
| Catalog | `numbers_catalog_normalized` | Cross-provider UI + `field_verification` |

## Contours (do not mix)

| Contour | Purpose | Writes |
|---|---|---|
| **A. Inventory** | Load FN free numbers via `OPERATOR_INN` / provider sync | Catalog rows (msisdn, presence, …) |
| **B. Operator cache** | by-inn ranges for enabled INNs in Settings | **Only** `catalog.operator` |

## CONTRACT_BACKED vs OPERATIONAL

- **CONTRACT_BACKED:** which HTTP methods/actions run; which fields are extracted from provider docs/APIs.
- **OPERATIONAL:** `sync_runs` / `sync_jobs`, wipe-guard, bulk/ORM persist, pagination of our API, UI polling, schedule.

## Sync model

- Primary UI/API path: `POST /api/v1/sync/start` (unified only).
- Modes: `full` (dictionaries + free + purchased) and `free_only` (Finenumbers).
- Production reload: stage into durable **UNLOGGED** tables (not TEMP — unsafe with connection pooling), then atomic wipe+cutover per `(provider, inventory_kind)`. `reload_allowed` refuses **empty** wipe only (size may shrink or grow); per-provider pagination/completeness gates apply where documented (UIS/Vox/MCN/…); there is no global ~90% size-ratio wipe-guard.
- Auth: `ADMIN_USERNAME` + `ADMIN_PASSWORD` enable UI login. Optional `ADMIN_API_TOKEN` on **backend** is additive for machine/CI. `DID_REQUIRE_AUTH=1` refuses boot without login credentials. UI uses Next `/api/backend` proxy with the browser session token only — frontend must not receive/inject the machine token.

## Adding a provider

1. Add docs under `docs/providers/<code>/` (or code contract if API is owned)
2. Implement `backend/app/providers/<code>/` layers
3. Register in `registry.py` + seed `providers` row
4. Add raw tables if needed + migration
5. Wire stage in unified progress plan
