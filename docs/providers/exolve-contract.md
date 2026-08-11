# Exolve (МТС Exolve) — machine contract

Sources (local artifacts win — see [`exolve/SOURCE.md`](exolve/SOURCE.md)):
- [`exolve/raw/Exolve-GetList.md`](exolve/raw/Exolve-GetList.md) — https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/
- [`exolve/raw/Exolve-GetFree.md`](exolve/raw/Exolve-GetFree.md) — https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/
- [`exolve/raw/Exolve-getting-api-key.md`](exolve/raw/Exolve-getting-api-key.md) — https://docs.exolve.ru/docs/ru/instructions/getting-api-key

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
1. `random` must be false / omitted (stable pagination).
2. Primary fetch = **type × every region_id** from GetList:
   - DEF `1104` × all regions
   - ABC `1105` × all regions
   - KDU `1106` × Russia `10084` only (docs)
3. Do **not** pass `category_id` in primary loop (all marketing categories in slice).
4. Paginate each slice until short/empty page; `offset > MAX_OFFSET` → fail `EXOLVE_PAGINATION_TRUNCATED` (no wipe).
5. Merge slices; dedupe by normalized `number_code`.

## NumberElement → catalog (summary)

| API | Catalog |
|---|---|
| `number_code` | `msisdn` / `provider_number_key` |
| `install_fee` | `buy_price` |
| `subscription_fee` | `period_price` |
| `type_name` | `number_type` |
| `category_name` | `class` (`number_class`) |
| geo | city/region via lookup + response fallback |
| — | `status_raw=free` |
