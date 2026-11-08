# Runexis documentation sources

## Dual surface (do not mix method SoT)

| Surface | Base (docs) | Inventory role | Artifact |
|---|---|---|---|
| **DIDAPI** (Scribe HTML) | `https://didapi.runexis.ru` | Purchased partner inventory, Bearer auth, regions/cities | [`raw/Runexis.html`](raw/Runexis.html) |
| **Numbering API** (live help) | `https://did-api.runexis.ru/` | **Sole** source for free / purchasable catalog | [help.runexis.ru/api/numbering_api](https://help.runexis.ru/api/numbering_api) (checked `2026-11-04T21:36:14Z`). DOCX/txt in `raw/` are an archive |

## DIDAPI (purchased / dictionaries)

- Copied from: `/Users/dvpershin/Downloads/API/Runexis/Runexis.html`
- Product title: DIDAPI Documentation (Scribe)
- Scope: auth (Bearer), regions/cities, **purchased** (`GET api/v1/numbers/management` non-free), CRM search, etc.
- Derived: [`../runexis-contract.md`](../runexis-contract.md)

## Numbering API (free catalog)

- Canonical, changeable text: [https://help.runexis.ru/api/numbering_api](https://help.runexis.ru/api/numbering_api)
- Checked: `2026-11-04T21:36:14Z` (Sergey Lependin). Re-read the page before changing free-number sync.
- Archive only: `/Users/dvpershin/Downloads/Runexis Numbering API.docx` → `raw/Runexis-Numbering-API.docx`
- Protocol: JSON-RPC 2.0 over POST (`application/x-www-form-urlencoded`, form field `jsonrpc`)
- Derived: [`../runexis-numbering-api-contract.md`](../runexis-numbering-api-contract.md)

## Derived docs (all)

- [`../runexis-contract.md`](../runexis-contract.md) — DIDAPI
- [`../runexis-numbering-api-contract.md`](../runexis-numbering-api-contract.md) — Numbering / free
- [`../runexis-field-mapping.md`](../runexis-field-mapping.md)
- [`../runexis-implementation-notes.md`](../runexis-implementation-notes.md)
- Code: `backend/app/providers/runexis/contract.py`

## Rules

1. For DIDAPI, the uploaded HTML wins over code and memory. For free numbers, the live Numbering API help page wins over the archived DOCX.
2. For **free / available-for-purchase** numbers, the method source of truth is the live Numbering API help page. The DOCX is an archive. A field the page does not describe stays as observed on live `search_numbers`.
3. For **purchased** partner inventory and DIDAPI REST auth/dictionaries, **only** `Runexis.html` applies.
4. Never call mutating Numbering/DIDAPI number actions from sync or probes (see `.cursor/rules/provider-api-read-only.mdc`).
