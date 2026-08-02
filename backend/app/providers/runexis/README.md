# Runexis provider

Documentation-driven integration with two APIs:

- **DIDAPI** (HTML): auth, regions/cities, purchased inventory via `GET api/v1/numbers/management`
- **Numbering API** (DOCX): free/purchasable catalog via JSON-RPC `connect` + `search_numbers`

Sources:

- `docs/providers/runexis/raw/Runexis.html`
- `docs/providers/runexis/SOURCE.md` + Numbering contract
- `docs/providers/runexis-contract.md`
- `docs/providers/runexis-field-mapping.md`

## Auth

- DIDAPI: `email` / `password` → Bearer via `POST api/v1/login`, refresh via `POST api/v1/refresh`
- Numbering: separate `numbering_login` / `numbering_password` (+ optional `numbering_base_url`, partition)

## Inventory

- **Free:** Numbering API `search_numbers` with free filters (parallel paginated listing)
- **Purchased:** DIDAPI management list excluding free statuses

Provider APIs are used read-only.
