# Provider documentation artifacts

## Source of truth

Uploaded HTML files are the **only** specification for external provider APIs:

- Runexis: [`runexis/raw/Runexis.html`](runexis/raw/Runexis.html)
- SipOut: [`sipout/raw/SipOut.html`](sipout/raw/SipOut.html)

Derived artifacts (`*-contract.md`, `*-field-mapping.md`, `*-implementation-notes.md`) must not invent methods, fields, or semantics beyond those files.

## Markers

| Marker | Meaning |
|---|---|
| VERIFIED | Explicitly described in formal docs prose/param tables |
| EXAMPLE-CONFIRMED | Appears only in example JSON |
| UNVERIFIED | Not confirmed — isolate, mark `TODO: VERIFY_WITH_DOC_FILE`, keep raw |

## Strict mode

If documentation is insufficient: isolate uncertainty, keep `raw_payload`, stop short of unsafe assumptions.
