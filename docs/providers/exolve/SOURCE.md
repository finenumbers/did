# Exolve documentation source

- Portal: [Exolve Docs](https://docs.exolve.ru/)
- Free inventory: [GetFree](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/)
- Reference dictionaries: [GetList (справочник)](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/)
- Auth: [Как получить API-ключ приложения](https://docs.exolve.ru/docs/ru/instructions/getting-api-key)

## Artifacts

| File | Source page |
|---|---|
| [`raw/Exolve-GetFree.html`](raw/Exolve-GetFree.html) | GetFree — free numbers available for purchase |
| [`raw/Exolve-GetFree.md`](raw/Exolve-GetFree.md) | Same page, readable markdown extract |
| [`raw/Exolve-GetList.html`](raw/Exolve-GetList.html) | GetList — types / categories / regions reference |
| [`raw/Exolve-GetList.md`](raw/Exolve-GetList.md) | Same page, readable markdown extract |
| [`raw/Exolve-getting-api-key.html`](raw/Exolve-getting-api-key.html) | How to obtain application API key |
| [`raw/Exolve-getting-api-key.md`](raw/Exolve-getting-api-key.md) | Same page, readable markdown extract |

## Rule

Saved artifacts under `exolve/raw/` are the method source of truth for Exolve. Derived `exolve-contract.md` / `exolve-field-mapping.md` must not invent methods or fields. Integration is **read-only** (`GetList` + `GetFree` only; Lock / Buy / purchased inventory are out of scope).

The short region table in the GetFree article is an excerpt — the full region set comes from GetList `regions[]`.
