# Exolve (МТС Exolve) — machine contract

Nav: [`exolve/SOURCE.md`](exolve/SOURCE.md) · [`exolve-field-mapping.md`](exolve-field-mapping.md) · [`exolve-implementation-notes.md`](exolve-implementation-notes.md) · code `backend/app/providers/exolve/contract.py`

Sources (local artifacts win — see [`exolve/SOURCE.md`](exolve/SOURCE.md)):
- [`exolve/raw/Exolve-Numbering-API.md`](exolve/raw/Exolve-Numbering-API.md) — https://docs.exolve.ru/docs/ru/api-reference/numbering-api (full method index)
- [`exolve/raw/Exolve-GetList.md`](exolve/raw/Exolve-GetList.md) — https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/
- [`exolve/raw/Exolve-GetFree.md`](exolve/raw/Exolve-GetFree.md) — https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/
- [`exolve/raw/Exolve-getting-api-key.md`](exolve/raw/Exolve-getting-api-key.md) — https://docs.exolve.ru/docs/ru/instructions/getting-api-key
- [`exolve/raw/Exolve-buying-number.md`](exolve/raw/Exolve-buying-number.md) — https://docs.exolve.ru/docs/ru/instructions/buying-number/
- Out-of-scope methods also archived under `exolve/raw/` (Lock, Unlock, Buy, Delete, customer GetList, GetInfo, forwarding, AMD, GetAttributes) — see SOURCE.md

## Auth

- Header: `Authorization: Bearer <api_key>`
- API key is configured only in web **Settings** → Exolve card (`provider_connections.auth_settings.api_key`).
- Default base URL: `https://api.exolve.ru`

## Read-only boundary

Allowed:
- `POST /number/reference/v1/GetList` — dictionaries
- `POST /number/v1/GetFree` — free inventory

Never call: Lock, Unlock, Buy, Delete, purchased GetList, forwarding, or any mutating Numbering API.

## GetList (reference)

- Body: `{}`
- Returns `types`, `categories`, `regions` (full region set — do not use the short GetFree article table).

Region fields: `project_id`, `region_id`, `parent_region_id`, `region_code`, `region_name` (Latin), `description` (Cyrillic).

**Completeness:** persist every `regions[]` row. Empty reference regions → fail dictionaries.

## GetFree (free numbers)

Required: `type_id`.  
Optional filters: `region_id`, `category_id`, `mask`, `limit`, `offset`, `random`.

Sync rules (completeness):
1. Prefer **omitting** `random` for inventory pagination. Docs demos use `random: true`; canary also probes that shape. Do not use `random: true` in the production loop.
2. Live canary decides slice mode:
   - **Docs examples** (with `category_id` + `random: true`, e.g. Moscow DEF/`10000`, Moscow ABC/`10001`) vs **no-category** probes.
   - If docs examples return numbers and no-category probes are empty → sync = **type × region × category** (categories from GetList `categories[]` for that `type_id`; fallback to docs category table).
   - Otherwise → sync = **type × region** without `category_id`.
3. Region fan-out (docs types only):
   - DEF `1104` × all GetList region_ids
   - ABC `1105` × all GetList region_ids
   - KDU `1106` × Russia `10084` only
4. Paginate each slice until an **empty** page (`DEFAULT_PAGE_LIMIT = 500`; docs do not state a max). A short (non-full) page advances `offset` by `len(page)` and continues — do not treat short as end. If a page is empty after the slice already has items, retry the **same** offset once (transient empty guard); still empty → end. `offset > MAX_OFFSET` → fail `EXOLVE_PAGINATION_TRUNCATED` (no wipe).
5. Merge slices; dedupe by normalized `number_code`.
6. If all slices empty **and** docs-example canary is also 0 → fail with explicit LK inventory/balance message.

## Sync stages (product) — OPERATIONAL

| Stage id | Phase |
|---|---|
| `exolve_dictionaries` | GetList |
| `exolve_free` | GetFree |

## NumberElement → catalog (summary)

| API | Catalog |
|---|---|
| `number_code` | `msisdn` / `provider_number_key` |
| `install_fee` | `buy_price` |
| `subscription_fee` | `period_price` |
| `type_name` | `number_type` |
| `category_name` | `class` (`number_class`) |
| geo | city/region via lookup + response fallback |
| — | DTO `status_raw=free` (ingest only, not a catalog column) |
