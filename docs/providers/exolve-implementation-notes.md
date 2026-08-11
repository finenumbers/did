# Exolve implementation notes

See completeness/API rules in [`exolve-contract.md`](exolve-contract.md). This file is operational only.

## Settings

| Key | Purpose |
|---|---|
| `auth_settings.api_key` | Bearer application API key (ЛК → Приложения) |
| `base_url` | Default `https://api.exolve.ru` |

## Sync stages

| Stage id | Phase |
|---|---|
| `exolve_dictionaries` | GetList → regions/cities/categories raw |
| `exolve_free` | GetFree fan-out type × region → staging cutover |

## Operational

1. **test_connection:** short GetList probe; UI message `Exolve OK` on success.
2. Free sync walks docs SYNC types × regions (canary chooses type×region vs type×region×category).
3. Persist: UNLOGGED staging → wipe free → cutover (`persist_exolve_numbers`); wipe-guard refuses empty incoming only (no size-ratio).
4. Purchased / Lock / Buy never called.
5. After provider cutovers, Contour B (Finenumbers) operator enrichment still runs.

## Code

`backend/app/providers/exolve/` — `contract.py`, `client.py`, `provider.py`.
