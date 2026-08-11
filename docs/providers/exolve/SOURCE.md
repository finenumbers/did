# Exolve documentation source

- Portal: [Exolve Docs](https://docs.exolve.ru/)
- Free inventory: [GetFree](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/)
- Reference dictionaries: [GetList (справочник)](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/)
- Auth: [Как получить API-ключ приложения](https://docs.exolve.ru/docs/ru/instructions/getting-api-key)
- Purchase flow: [Как купить номер](https://docs.exolve.ru/docs/ru/instructions/buying-number/)

## Artifacts

| File | Source page |
|---|---|
| [`raw/Exolve-GetFree.html`](raw/Exolve-GetFree.html) | GetFree — free numbers available for purchase |
| [`raw/Exolve-GetFree.md`](raw/Exolve-GetFree.md) | Same page, readable markdown extract |
| [`raw/Exolve-GetList.html`](raw/Exolve-GetList.html) | GetList — types / categories / regions reference |
| [`raw/Exolve-GetList.md`](raw/Exolve-GetList.md) | Same page, readable markdown extract |
| [`raw/Exolve-getting-api-key.html`](raw/Exolve-getting-api-key.html) | How to obtain application API key |
| [`raw/Exolve-getting-api-key.md`](raw/Exolve-getting-api-key.md) | Same page, readable markdown extract |
| [`raw/Exolve-buying-number.md`](raw/Exolve-buying-number.md) | Buy flow + Postman GetFree example with `category_id` |

## Note on GetFree examples

Every documented GetFree success example includes `category_id` and usually `random: true`, even though the param table marks them optional. Live canaries compare docs-shaped requests vs no-category probes before choosing sync mode.

## Rule

Saved artifacts under `exolve/raw/` are the method source of truth for Exolve. Derived `exolve-contract.md` / `exolve-field-mapping.md` must not invent methods or fields. Integration is **read-only** (`GetList` + `GetFree` only; Lock / Buy / purchased inventory are out of scope).

The short region table in the GetFree article is an excerpt — the full region set comes from GetList `regions[]`.
