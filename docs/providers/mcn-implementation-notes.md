# MCN Telecom implementation notes

See completeness/API rules in [`mcn-contract.md`](mcn-contract.md). This file is operational only.

## Settings

| Key | Purpose |
|---|---|
| `auth_settings.api_key` | Integrations token (ЛК → Интеграции → Токены) |
| `auth_settings.auth_header_mode` | Persisted after probe: `bearer` / `raw` / `x_auth_token` |
| `base_url` | Default `https://shop.mcn.ru` |

OpenAPI does not declare `securitySchemes`; header mode is discovered on test_connection / first sync.

## Sync stages

| Stage id | Phase |
|---|---|
| `mcn_dictionaries` | countries + regions + cities RU |
| `mcn_free` | showcase/numbers (country-wide or city fan-out) |

## Operational

1. **test_connection:** probe auth modes on `GET …/showcase/countries`; require `countryCode=643` present; persist working mode.
2. Page size probe: `limitPerPage` 25 → 100 → 200; keep largest accepted.
3. Prefer country-wide paging; fan-out cities with `free_numbers_count > 0` if country-wide incomplete/unstable.
4. Slice shortfall → `MCN_SLICE_INCOMPLETE` / job `MCN_FREE_INCOMPLETE`.
5. Concurrency ≤ 3 on city fan-out; retry 429/5xx.
6. Persist: TEMP staging wipe+cutover (`persist_mcn_numbers`).
7. Checkout / NNP / purchased out of scope (NNP archived under `mcn/raw/` as non-inventory).

## Code

`backend/app/providers/mcn/` — `client.py`, `provider.py`, `contract.py`.
