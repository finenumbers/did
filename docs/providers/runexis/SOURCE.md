# Runexis documentation sources

## Primary REST partner API (purchased / CRM / dictionaries)

- Copied from: `/Users/dvpershin/Downloads/API/Runexis/Runexis.html`
- Artifact: `docs/providers/runexis/raw/Runexis.html`
- Product title: DIDAPI Documentation (Scribe)
- Base URL (docs): `https://didapi.runexis.ru`
- Scope in this project: auth (Bearer), regions/cities, **purchased** partner inventory (`GET api/v1/numbers/management` non-free), CRM search, etc.

## Additional Numbering API (free / purchasable catalog) — sole source for that inventory

- Copied from: `/Users/dvpershin/Downloads/Runexis Numbering API.docx`
- Artifacts:
  - `docs/providers/runexis/raw/Runexis-Numbering-API.docx` (original)
  - `docs/providers/runexis/raw/Runexis-Numbering-API.txt` (extracted text for search/diff)
- Derived contract: `docs/providers/runexis-numbering-api-contract.md`
- Product title: Numbering API
- Base URL (docs): `https://did-api.runexis.ru/`
- Protocol: JSON-RPC 2.0 over POST (`application/x-www-form-urlencoded`, form field `jsonrpc`)
- Scope in this project: **only** free / available-for-purchase numbering discovery and related **read** dictionaries

## Rules

1. Uploaded files win over code, memory, and internet.
2. For **free / available-for-purchase** Runexis numbers, **only** Numbering API (`Runexis-Numbering-API.docx`) is the method source of truth.
3. For **purchased** partner inventory and DIDAPI REST auth/dictionaries, **only** `Runexis.html` applies.
4. Never call mutating Numbering/DIDAPI number actions from sync or probes (see `.cursor/rules/provider-api-read-only.mdc`).
