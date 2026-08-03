# UIS implementation notes

## Auth settings keys

| Key | Purpose |
|---|---|
| `access_token` | Permanent/temporary API key (preferred for sync) |
| `login` / `password` | Fallback → `login.user` when token empty |
| `user_id` | Optional agent customer user id (number as string in settings) |
| `session_expire_at` | Stored after login.user (operational) |

## Operational

1. **IP whitelist**: add Docker/host egress IP in UIS ЛК → API security, or `0.0.0.0/0` for lab.
2. Use host `dataapi.uiscom.ru` with UIS credentials (not Comagic).
3. Page size default 1000 (docs default); max 10000 — client uses 1000 unless overridden.
4. Phone normalize: strip non-digits; `8XXXXXXXXXX` → `7…`; 10-digit national → prefix `7`.
5. Empty free/purchased fetch must not wipe (existing wipe-guard).
6. Contour B (Finenumbers operator enrich) still runs after all providers including UIS.

## Test connection

1. Resolve token (stored or login.user).
2. `get.virtual_numbers` with `limit=1`.
3. Persist refreshed session token into auth_settings when obtained via login.
