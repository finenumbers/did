# Architecture

## Boundaries

```
UI (Next.js) → Admin API (FastAPI) → Sync engine → Providers registry
                                              ↓
                         provider.py → client → parser → mapper
                                              ↓
                         raw tables → numbers_catalog_normalized → history
```

## Modules

| Area | Path | Role |
|---|---|---|
| Providers | `backend/app/providers/` | Doc-driven adapters (contract/client/parser/mapper/provider) |
| Sync | `backend/app/modules/sync_engine/` | Jobs, fetch/persist, soft-absence, dry-run |
| Settings | DB `provider_connections` + API | Auth/base URL/test connection |
| Catalog | `numbers_catalog_normalized` | Cross-provider UI with `field_verification` |

## CONTRACT_BACKED vs OPERATIONAL

- **CONTRACT_BACKED:** which HTTP methods/actions run; which fields are extracted; SipOut free/purchased/geo; Runexis me/regions/cities; Runexis free/purchased limitations.
- **OPERATIONAL:** job tables, upsert hashes, soft-absence, pagination of our API, dry-run, UI polling.

## Adding a provider

1. Add uploaded docs under `docs/providers/<code>/raw/`
2. Write `*-contract.md` and `*-field-mapping.md`
3. Implement `backend/app/providers/<code>/` layers
4. Register in `registry.py` + seed `providers` row
5. Add raw tables if needed + migration
