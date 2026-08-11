# UIS implementation notes

Nav: [`uis/SOURCE.md`](uis/SOURCE.md) · [`uis-contract.md`](uis-contract.md) · [`uis-field-mapping.md`](uis-field-mapping.md)

## Auth settings keys

| Key | Purpose |
|---|---|
| `access_token` | Permanent/temporary API key from UIS ЛК (required) |
| `user_id` | Optional agent customer user id (number as string in settings) |

Product does **not** call `login.user`; session-via-password is unused. Vendor docs still describe that method separately.

## Sync stages

| Stage id | Phase |
|---|---|
| `uis_free` | `get.available_virtual_numbers` |
| `uis_purchased` | `get.virtual_numbers` |

## Operational

1. **IP whitelist**: add Docker/host egress IP in UIS ЛК → API security, or `0.0.0.0/0` for lab.
2. Use host `dataapi.uiscom.ru` with UIS credentials (not Comagic).
3. Page size default 1000 (docs default); max 10000 — client uses 1000 unless overridden.
4. Pagination: do not stop on short page while `offset < total_items`. `UIS_PAGINATION_TRUNCATED` only when hit `MAX_OFFSET` with `fetched < total_items`. Empty page inside the window with shortfall → `total_items_mismatch` warning, sync continues (no fail).
5. Blank/whitespace `base_url` falls back to `https://dataapi.uiscom.ru/v2.0`.
6. Phone normalize: strip non-digits; `8XXXXXXXXXX` → `7…`; 10-digit national → prefix `7`.
7. Empty free/purchased fetch must not wipe (existing wipe-guard).
8. Contour B (Finenumbers operator enrich) still runs after all providers including UIS.

## Test connection

1. Require stored `access_token`.
2. `get.virtual_numbers` with `limit=1`.
