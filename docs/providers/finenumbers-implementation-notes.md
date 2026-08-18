# Finenumbers implementation notes

Nav: [`finenumbers/SOURCE.md`](finenumbers/SOURCE.md) · [`finenumbers-contract.md`](finenumbers-contract.md) · [`finenumbers-field-mapping.md`](finenumbers-field-mapping.md)

## Settings

| Key | Purpose |
|---|---|
| `auth_settings.key` | Bearer token (alias `api_key` accepted by client) |
| `base_url` | Default `https://pstn.finenumbers.com` |

## Sync stages

| Stage id | Phase |
|---|---|
| `finenumbers_free` | Contour A by-inn expand → catalog (no dictionaries stage) |
| `finenumbers_purchased` | Contour C REG → purchased + provisional RTU flags |
| `finalize` | Dropped XLSX, inventory summary, catalog checksum |
| `operator_enrichment` | **Last** stage: Contour B fills `operator` and overlays `city_name`/`region_name` from `garTerritory` on all present rows; then RTU flags re-applied |

## Contour C — REG / RTU (purchased)

- REG-only inserts under provider `finenumbers`; duplicates already purchased elsewhere are skipped (no second row).
- Column **Подключено в РТУ**:
  - **Своя нумерация** — Finenumbers + operator Frontier
  - **Внешняя нумерация** — Finenumbers + non-Frontier operator, or other provider present in REG
  - **Не подключено** — other provider absent from REG
- Yellow row = Внешняя; red row = Не подключено.

## Contour A — free inventory

- Provider code: `finenumbers`.
- Unified sync mode: `full` (Contour A free + Contour C purchased/RTU; no dictionaries API).
- Flow: `lookup/by-inn` pages → expand ranges → wipe `(finenumbers, free)` if `reload_allowed` → catalog insert (no raw table).
- Operator column for these rows is filled later by Contour B enrichment (same as other providers).

## Contour B — PSTN INN operator cache

- Settings UI: CRUD operators + «Загрузить кеш».
- Tables: `pstn_inn_cache_operators`, `pstn_inn_ranges_cache` (includes `gar_territory`).
- Refresh pulls `by-inn` ranges per enabled operator (`operator`, `region`, `garTerritory`).
- Enrichment (`enrich_catalog_operators`) runs as the **last** unified-sync stage after `finalize`.
- Every currently present free/purchased row: local ranges first; cache miss → always `lookup?phone=` (no skip for already-filled operator).
- Successful cache/API value **overwrites** existing `operator`.
- When `garTerritory` is present, overlay **both** `city_name` and `region_name` even if operator did not change. Empty GAR leaves catalog geo NULL (not provider geo, not PSTN `region`), except found **800** (see below).
- Terminal PSTN miss (`found=false` / empty / invalid MSISDN / HTTP 400|404|422) → **`Нет в реестре`** on `operator`, `city_name`, and `region_name` for **any** category (including 800); blue row in UI/XLSX; counts as covered.
- Found **Бесплатный вызов** (`800`): city/region = **`Российская Федерация`** (ignore GAR); operator still from cache/lookup. Empty GAR still writes РФ.
- Found **Мобильный**: collapse Москва/Московская область and Санкт-Петербург/Ленинградская область so both columns are the city. Geographic ABC keeps GAR as parsed.
- Transport/5xx/auth lookup errors: client retries 5xx; enrich re-queues across waves; unresolved → do **not** write sentinel, do **not** clear existing operator/geo, fail `require_full_coverage` with status/body in logs.
- Final `operator` SoT is PSTN enrich (or the sentinel above). GAR overlay is SoT for city/region when the field is present; sentinel is SoT on terminal miss.
- After deploy: press «Загрузить кеш», then sync. Gate refuses start until a non-empty `gar_territory` exists. If enrich still sees 0 GAR, it refreshes by-inn once and fails if still empty.

## Sync gate

- `require_min_cache_ready` / `is_min_cache_ready`: all `REQUIRED_OPERATORS` INNs enabled with `ranges_count > 0`, **and** at least one cached range has non-empty `gar_territory`.
- If enrich seeds ranges with `seeded_with_gar=0`, it calls `refresh_enabled_caches` (same as «Загрузить кеш») once and re-seeds. Still 0 → fail enrich (`PSTN_GAR_CACHE_EMPTY`), run `partial`.
- Scheduler 00:00 Europe/Moscow skips if cache not ready or sync already running.
- Unified `POST /api/v1/sync/start` returns error if cache not ready or refresh running.
- Operator enrichment failure after successful provider cutovers → run status `partial`; catalog is not rolled back.

## Separation invariant

Do not treat Contour A free inventory as Contour B cache, and do not let Contour B wipe inventory or rewrite prices/status. Contour B may overlay `city_name`/`region_name` from `garTerritory` only.
