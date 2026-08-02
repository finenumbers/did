# Finenumbers PSTN contract

Source of truth for integration: `backend/app/providers/finenumbers/contract.py` and live PSTN API.
Vendor HTML/PDF materials are not checked into this repo; markers below reflect code-confirmed usage.

## Contours (do not mix)

| Contour | Purpose | Storage / writes |
|---|---|---|
| **A — inventory** | Free numbers for operator ИНН «Фронтир» (`5406978329`) as a provider inventory slice | `numbers_catalog_normalized` via Finenumbers sync (`free_only`) |
| **B — operator cache** | PSTN ranges by INN for catalog column **Оператор** | `pstn_inn_cache_operators` / `pstn_inn_ranges_cache`; enrich writes **only** `catalog.operator` |

Same INN may appear in both contours (e.g. Frontier). Contour A loads numbers; Contour B resolves operators for any provider’s catalog rows.

## Auth — VERIFIED (code)

- Bearer token in `Authorization` header.
- Setting key: `auth_settings.key` (alias `api_key` accepted by client).

## Base URL — EXAMPLE

`https://pstn.finenumbers.com`

## Endpoints used — VERIFIED (code)

| Path | Use |
|---|---|
| `GET /api/v1/lookup/by-inn` | Contour A inventory + Contour B cache refresh; query `inn`, `page`, `pageSize` |
| `GET /api/v1/lookup` | Contour B fallback enrichment; query `phone=` |

## Rate limit — VERIFIED (code)

- Platform: 5000 req/min.
- Client safe budget: 4800 req/min (token bucket).

## Contour A defaults

- Operator INN for free inventory: `5406978329`.
- Default page size: 100.
- Ranges expanded into individual catalog MSISDNs in mapper.

## Contour B min set (sync gate)

Manual cache load must cover before unified sync starts:

| Operator | INN |
|---|---|
| ООО «СИПАУТНЭТ» | `5920032027` |
| ООО «ИНТЕРНОД» | `7733808377` |
| ООО «Фронтир Нетворк» | `5406978329` |

Sync does **not** auto-refresh Contour B. Cache refresh is manual from Settings.

## Capabilities in product

| Capability | Supported |
|---|---|
| free numbers (by-inn expand) | yes |
| purchased numbers | no |
| dictionaries (regions/cities) | no |
| test connection | yes (`by-inn` page=1) |
| operator enrichment | yes (local cache first, then lookup) |

## Read-only

All Finenumbers calls are read-only. No mutating PSTN operations.
