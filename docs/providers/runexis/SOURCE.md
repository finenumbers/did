# Runexis documentation sources

## Dual surface (do not mix method SoT)

| Surface | Base (docs) | Inventory role | Artifact |
|---|---|---|---|
| **DIDAPI** (Scribe HTML) | `https://didapi.runexis.ru` | Purchased partner inventory, Bearer auth, regions/cities | [`raw/Runexis.html`](raw/Runexis.html) |
| **Numbering API** (DOCX) | `https://did-api.runexis.ru/` | **Sole** source for free / purchasable catalog | [`raw/Runexis-Numbering-API.docx`](raw/Runexis-Numbering-API.docx) + [`.txt`](raw/Runexis-Numbering-API.txt) |

## DIDAPI (purchased / dictionaries)

- Copied from: `/Users/dvpershin/Downloads/API/Runexis/Runexis.html`
- Product title: DIDAPI Documentation (Scribe)
- Scope: auth (Bearer), regions/cities, **purchased** (`GET api/v1/numbers/management` non-free), CRM search, etc.
- Derived: [`../runexis-contract.md`](../runexis-contract.md)

## Numbering API (free catalog)

- Copied from: `/Users/dvpershin/Downloads/Runexis Numbering API.docx`
- Protocol: JSON-RPC 2.0 over POST (`application/x-www-form-urlencoded`, form field `jsonrpc`)
- Derived: [`../runexis-numbering-api-contract.md`](../runexis-numbering-api-contract.md)

## Derived docs (all)

- [`../runexis-contract.md`](../runexis-contract.md) — DIDAPI
- [`../runexis-numbering-api-contract.md`](../runexis-numbering-api-contract.md) — Numbering / free
- [`../runexis-field-mapping.md`](../runexis-field-mapping.md)
- [`../runexis-implementation-notes.md`](../runexis-implementation-notes.md)
- Code: `backend/app/providers/runexis/contract.py`

## Rules

1. Uploaded files win over code, memory, and internet.
2. For **free / available-for-purchase** numbers, **only** Numbering API DOCX is the method source of truth.
3. For **purchased** partner inventory and DIDAPI REST auth/dictionaries, **only** `Runexis.html` applies.
4. Never call mutating Numbering/DIDAPI number actions from sync or probes (see `.cursor/rules/provider-api-read-only.mdc`).
