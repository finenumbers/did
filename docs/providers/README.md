# Provider documentation artifacts

## Source of truth

External provider APIs are documented from uploaded vendor materials:

- **SipOut:** [`sipout/raw/SipOut.html`](sipout/raw/SipOut.html) (HTML)
- **Runexis DIDAPI:** [`runexis/raw/Runexis.html`](runexis/raw/Runexis.html) (HTML)
- **Runexis Numbering API:** see [`runexis/SOURCE.md`](runexis/SOURCE.md) and `runexis-numbering-api-contract.md` (DOCX-derived)
- **Finenumbers / PSTN:** [`finenumbers-contract.md`](finenumbers-contract.md), [`finenumbers-implementation-notes.md`](finenumbers-implementation-notes.md) (Contour A inventory vs Contour B operator cache); code constants in `backend/app/providers/finenumbers/contract.py`
- **UIS Data API:** see [`uis/SOURCE.md`](uis/SOURCE.md), [`uis-contract.md`](uis-contract.md), [`uis-field-mapping.md`](uis-field-mapping.md); raw HTML under [`uis/raw/`](uis/raw/); code in `backend/app/providers/uis/contract.py`
- **Aurora Telecom:** see [`aurora/SOURCE.md`](aurora/SOURCE.md), [`aurora-contract.md`](aurora-contract.md), [`aurora-field-mapping.md`](aurora-field-mapping.md); sample CSV under [`aurora/raw/`](aurora/raw/); code in `backend/app/providers/aurora/contract.py`
- **Exolve (МТС Exolve):** see [`exolve/SOURCE.md`](exolve/SOURCE.md), [`exolve-contract.md`](exolve-contract.md), [`exolve-field-mapping.md`](exolve-field-mapping.md); raw HTML/MD under [`exolve/raw/`](exolve/raw/) (incl. buying-number); code in `backend/app/providers/exolve/contract.py`
- **Voximplant:** see [`voximplant/SOURCE.md`](voximplant/SOURCE.md), [`voximplant-contract.md`](voximplant-contract.md), [`voximplant-field-mapping.md`](voximplant-field-mapping.md); raw HTML/MD under [`voximplant/raw/`](voximplant/raw/); code in `backend/app/providers/voximplant/contract.py`

Derived artifacts (`*-contract.md`, `*-field-mapping.md`, `*-implementation-notes.md`) must not invent methods, fields, or semantics beyond those sources.

## Markers

| Marker | Meaning |
|---|---|
| VERIFIED | Explicitly described in formal docs prose/param tables |
| EXAMPLE-CONFIRMED | Appears only in example JSON |
| UNVERIFIED | Not confirmed — isolate, mark `TODO: VERIFY_WITH_DOC_FILE`, keep raw |

## Strict mode

If documentation is insufficient: isolate uncertainty, keep `raw_payload`, stop short of unsafe assumptions. Provider integrations are **read-only**.
