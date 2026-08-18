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
- When `garTerritory` is present, overlay **both** `city_name` and `region_name` even if operator did not change. Empty GAR leaves provider geo unchanged.
- Terminal PSTN miss (`found=false` / empty / invalid MSISDN / HTTP 400|404|422) → **`Нет в реестре`** (blue row in UI/XLSX); counts as covered for sync gate; geo not cleared.
- Transport/5xx/auth lookup errors: client retries 5xx; enrich re-queues across waves; unresolved → do **not** write sentinel, do **not** clear existing operator/geo, fail `require_full_coverage` with status/body in logs.
- Final `operator` SoT is PSTN enrich (or the sentinel above). GAR overlay is SoT for city/region when the field is present.
- After deploy: reload PSTN cache («Загрузить кеш»), then sync — old cache rows have NULL `gar_territory`.

## Sync gate

- `require_min_cache_ready` / `is_min_cache_ready`: all `REQUIRED_OPERATORS` INNs enabled with `ranges_count > 0`.
- Scheduler 00:00 Europe/Moscow skips if cache not ready or sync already running.
- Unified `POST /api/v1/sync/start` returns error if cache not ready or refresh running.
- Operator enrichment failure after successful provider cutovers → run status `partial`; catalog is not rolled back.

## Separation invariant

Do not treat Contour A free inventory as Contour B cache, and do not let Contour B wipe inventory or rewrite prices/status. Contour B may overlay `city_name`/`region_name` from `garTerritory` only.
