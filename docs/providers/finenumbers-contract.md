# Finenumbers PSTN contract

Nav: [`finenumbers/SOURCE.md`](finenumbers/SOURCE.md) · [`finenumbers-field-mapping.md`](finenumbers-field-mapping.md) · [`finenumbers-implementation-notes.md`](finenumbers-implementation-notes.md) · code `backend/app/providers/finenumbers/contract.py`

Source of truth for integration: `backend/app/providers/finenumbers/contract.py` and live PSTN API.
Vendor HTML/PDF materials are not checked into this repo; markers below reflect code-confirmed usage.

## Contours (do not mix)

| Contour | Purpose | Storage / writes |
|---|---|---|
| **A — inventory** | Free numbers for operator ИНН «Фронтир» (`5406978329`) as a provider inventory slice | `numbers_catalog_normalized` free via Finenumbers sync |
| **B — operator cache** | PSTN ranges by INN for catalog column **Оператор** | `pstn_inn_cache_operators` / `pstn_inn_ranges_cache`; enrich writes **only** `catalog.operator` |
| **C — REG / RTU** | Purchased endpoints from REG + column **Подключено в РТУ** | `GET https://reg.finenumbers.com/api/phones` (read-only); purchased + `rtu_connected` |

Same INN may appear in A/B (e.g. Frontier). Contour C uses a separate REG API key (`auth_settings.reg_key`).

## Contour C — REG — VERIFIED (sibling Reg project + code)

- Base URL default: `https://reg.finenumbers.com` (`extra_settings.reg_base_url`)
- Auth: `Authorization: Bearer reg_…` (`auth_settings.reg_key`)
- Read-only: `GET /api/phones?kind=endpoints_registered|endpoints_unregistered|endpoints_error`
- Number field: `endpointNumber`
- Free inventory = PSTN expand minus REG keys
- `rtu_connected` (purchased):
  - Finenumbers + Frontier operator (any PSTN/code spelling of ООО «Фронтир Нетворк») → **Своя нумерация**
  - Finenumbers + other/empty operator → **Внешняя нумерация** (yellow)
  - Other provider + number in REG → **Внешняя нумерация** (yellow; no duplicate catalog row)
  - Other provider + number not in REG → **Не подключено** (red)
- Flags are re-applied after Contour B operator enrichment (final `operator` SoT is PSTN enrich only; REG does not seed operator)
- **Never** call REG mutating endpoints (`POST …/request`, `rtu-import`, `regs/poll`, …)

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

Manual cache load must cover before unified sync starts. Source of truth: `REQUIRED_OPERATORS` in `backend/app/modules/pstn_inn_cache/service.py`.

| Operator | INN |
|---|---|
| ООО «СИПАУТНЭТ» | `5920032027` |
| ООО «ИНТЕРНОД» | `7733808377` |
| ООО «Фронтир Нетворк» | `5406978329` |
| ООО «НОВОСИСТЕМ» | `7710311878` |
| ООО «Аврора Телеком» | `7810833282` |
| АО «ЭР-Телеком Холдинг» | `5902202276` |
| АО «МТТ» | `7705017253` |
| ООО «МСН Телеком» | `7727752084` |
| ООО «Фастком» | `7702764401` |
| ООО «Миател» | `7841482919` |
| ООО «ДИАЛОГСИБИРЬ-БАРНАУЛ» | `2225058684` |
| ООО «СВЯЗЬ» | `2209025699` |
| ООО «СЕРВИС-КОММЮНИКЭЙШН» | `7707244004` |
| ООО «КМВтелеком» | `2626045442` |

Sync does **not** auto-refresh Contour B. Cache refresh is manual from Settings.

## Capabilities in product

| Capability | Supported |
|---|---|
| free numbers (by-inn expand) | yes |
| purchased numbers | no |
| dictionaries (regions/cities) | no |
| test connection | yes (`by-inn` page=1) |
| operator enrichment | yes (local cache first, then lookup) |

## Sync stages (product)

| Stage id | Phase |
|---|---|
| `finenumbers_free` | Contour A inventory only |

## Read-only

All Finenumbers calls are read-only. No mutating PSTN operations.
