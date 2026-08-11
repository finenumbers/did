# Voximplant implementation notes

See completeness/API rules in [`voximplant-contract.md`](voximplant-contract.md). This file is operational only.

## Settings

| Key | Purpose |
|---|---|
| `account_id`, `key_id`, `private_key` | Parsed from pasted Service Account `credentials.json` |
| `base_url` | Default `https://api.voximplant.com`; prefer `api_address` from GetAccountInfo when present |

UI accepts full JSON blob; upsert normalizes to structured keys (not stored as raw blob long-term).

## Sync stages

| Stage id | Phase |
|---|---|
| `voximplant_dictionaries` | RU categories + regions |
| `voximplant_free` | GetNewPhoneNumbers per stock category×region |

## Operational

1. **test_connection:** JWT → GetAccountInfo (+ categories canary). Roles: Owner / Admin / Accountant for listing.
2. Completeness: each slice paginated to `total_count`; shortfall → `VOXIMPLANT_SLICE_INCOMPLETE`.
3. Persist: TEMP staging wipe+cutover (`persist_voximplant_numbers`).
4. Attach / purchased APIs out of scope (archived under `voximplant/raw/`).
5. JWT RS256: `kid` in header, `iss=account_id`, `exp <= iat+3600`.

## Code

`backend/app/providers/voximplant/` — `auth_jwt.py`, `client.py`, `provider.py`.
