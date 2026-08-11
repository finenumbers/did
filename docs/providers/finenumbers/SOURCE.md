# Finenumbers / PSTN documentation source

Vendor HTML/PDF for PSTN API **are not checked into this repo**. Source of truth for integration:

1. Live PSTN API behavior
2. Code constants: `backend/app/providers/finenumbers/contract.py`
3. Derived docs below (must not invent endpoints beyond code-confirmed usage)

Portal (external, not archived): typically `https://pstn.finenumbers.com` (EXAMPLE base in contract).

## Why no `raw/` archive

Unlike SipOut/UIS/Exolve, no vendor document upload was committed. If materials appear later, place them under `finenumbers/raw/` and update this SOURCE with a product-used / archived table (same pattern as [`../exolve/SOURCE.md`](../exolve/SOURCE.md)).

## Contours (do not mix)

| Contour | Purpose | Docs |
|---|---|---|
| **A — inventory** | Free numbers for Frontier INN as provider `finenumbers` | contract + field-mapping |
| **B — operator cache** | PSTN ranges by INN → catalog column **Оператор** | contract + implementation-notes |

## Derived docs

- [`../finenumbers-contract.md`](../finenumbers-contract.md)
- [`../finenumbers-field-mapping.md`](../finenumbers-field-mapping.md)
- [`../finenumbers-implementation-notes.md`](../finenumbers-implementation-notes.md)

## Rule

Markers in derived docs use `VERIFIED (code)` where only code/live confirms behavior. Do not pretend vendor HTML exists in-repo. Read-only only.
