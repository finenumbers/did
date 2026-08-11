# SipOut documentation source

- Portal / ЛК API: документация «Документация API» в LK SipOut
- Original page title: Документация API - Личный кабинет Sipout
- Copied from local upload: `/Users/dvpershin/Downloads/API/SipOut/SipOut.html`

## Artifacts

| File | Source | Product use |
|---|---|---|
| [`raw/SipOut.html`](raw/SipOut.html) | Uploaded HTML (sole vendor capture) | Auth, DID actions (`get_cities`, `free_list`, `connected_list`), balance |

## Derived docs

- [`../sipout-contract.md`](../sipout-contract.md)
- [`../sipout-field-mapping.md`](../sipout-field-mapping.md)
- [`../sipout-implementation-notes.md`](../sipout-implementation-notes.md)
- Code: `backend/app/providers/sipout/contract.py`

## Rule

Uploaded HTML under `sipout/raw/` is the method source of truth. Derived contract/mapping must not invent methods or fields. Integration is **read-only** (`balance/get`, `did/get_cities`, `did/free_list`, `did/connected_list`).
