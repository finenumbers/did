# DIDWW — source of truth

## Portal

- Vendor docs: https://doc.didww.com/api3/2026-04-16/
- Getting started / auth: https://doc.didww.com/api3/configuration.html
- Production base URL: `https://api.didww.com/v3`
- API version pinned by the client: `X-Didww-Api-Version: 2026-04-16`

## Raw archive

No `raw/` folder: vendor HTML was not uploaded to the repo. Source of truth for DIDWW is the
online documentation above **plus** the code mirror `backend/app/providers/didww/contract.py`.
Any field not present in the online docs must stay `UNVERIFIED` and live only in
`raw_payload` of the `didww_*_raw` tables.

## Derived artifacts

| Artifact | Path |
|---|---|
| Machine contract | [`didww-contract.md`](../didww-contract.md) |
| Field mapping | [`didww-field-mapping.md`](../didww-field-mapping.md) |
| Implementation notes | [`didww-implementation-notes.md`](../didww-implementation-notes.md) |
| Code mirror | `backend/app/providers/didww/contract.py` |

## Scope rule

DIDWW is **not** part of the RU free-numbers catalog. It feeds its own section
(«Нумерация DIDWW», `/didww`) backed by `didww_catalog`, and never writes to
`numbers_catalog_normalized`. Integration is **read-only**: GET requests only, never
reservations, orders or `PATCH /dids`.
