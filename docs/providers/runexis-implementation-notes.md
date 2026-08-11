# Runexis implementation notes

## Dual API surface

| Surface | Base | Auth keys | Product use |
|---|---|---|---|
| DIDAPI (Scribe HTML) | `base_url` / `https://didapi.runexis.ru` | `email`, `password` → Bearer `token` | purchased, dictionaries, DIDAPI half of testConnection |
| Numbering API (DOCX) | `numbering_base_url` / `https://did-api.runexis.ru/` | `numbering_login`, `numbering_password`, optional `numbering_partition` → `numbering_session_id` | **free / purchasable** catalog |

## Implemented

| Operation | Implementation |
|---|---|
| DIDAPI login/refresh/me | `RunexisClient` |
| Numbering connect | `RunexisNumberingClient.connect` (read session only) |
| testConnection | DIDAPI `GET me` and/or Numbering `connect` when respective creds set |
| sync regions/cities | DIDAPI |
| sync purchased | DIDAPI `GET api/v1/numbers/management` exclude free mnemonic |
| sync free | Numbering `search_numbers` with free filter (`access_state` then fallback `usage_statuses`); parallel pages with early-cancel of higher offsets + sequential verify for completeness |

## Settings UI

Runexis panel has two credential blocks: DIDAPI + Numbering. Mutating Numbering/DIDAPI number methods are never called.

## Open / live-verify

- Exact `search_numbers` item JSON keys (parser is flexible; raw preserved)
- Whether live filter key is `access_state` or `usage_statuses`
- Whether `partition` is required for this account

## Forbidden

`reserv_numbers`, `book_numbers`, `sell_numbers`, DIDAPI book/buy, and other mutators — see `.cursor/rules/provider-api-read-only.mdc`.
