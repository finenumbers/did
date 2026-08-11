# Exolve documentation source

- Portal: [Exolve Docs](https://docs.exolve.ru/)
- **Numbering API overview (full method index):** [Numbering API](https://docs.exolve.ru/docs/ru/api-reference/numbering-api)
- Free inventory: [GetFree](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/)
- Reference dictionaries: [GetList (справочник)](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/)
- Purchased list (docs slug typo `purchsed`): [getting-purchsed-numbers](https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-purchsed-numbers/)
- Auth: [Как получить API-ключ приложения](https://docs.exolve.ru/docs/ru/instructions/getting-api-key)
- Purchase flow (instruction): [Как купить номер](https://docs.exolve.ru/docs/ru/instructions/buying-number/)

## Artifacts

Saved under [`raw/`](raw/). Prefer HTML as verbatim page capture; `.md` is a searchable extract.

### Overview + product-used (read-only integration)

| File | Source page | Product use |
|---|---|---|
| [`raw/Exolve-Numbering-API.html`](raw/Exolve-Numbering-API.html) / [`.md`](raw/Exolve-Numbering-API.md) | Numbering API overview (all methods on one page) | Full API index / cross-check |
| [`raw/Exolve-GetList.html`](raw/Exolve-GetList.html) / [`.md`](raw/Exolve-GetList.md) | GetList — types / categories / regions | **Sync dictionaries** |
| [`raw/Exolve-GetFree.html`](raw/Exolve-GetFree.html) / [`.md`](raw/Exolve-GetFree.md) | GetFree — free numbers for purchase | **Sync free inventory** |
| [`raw/Exolve-getting-api-key.html`](raw/Exolve-getting-api-key.html) / [`.md`](raw/Exolve-getting-api-key.md) | How to obtain application API key | Settings auth |
| [`raw/Exolve-buying-number.html`](raw/Exolve-buying-number.html) / [`.md`](raw/Exolve-buying-number.md) | Instruction: buy flow + Postman GetFree with `category_id` | Canary / docs examples |

### Archived for reference (out of product scope)

| File | Source page | Method |
|---|---|---|
| [`raw/Exolve-Lock.html`](raw/Exolve-Lock.html) / [`.md`](raw/Exolve-Lock.md) | locking-number | Lock |
| [`raw/Exolve-Unlock.html`](raw/Exolve-Unlock.html) / [`.md`](raw/Exolve-Unlock.md) | unlocking-number | Unlock |
| [`raw/Exolve-Buy.html`](raw/Exolve-Buy.html) / [`.md`](raw/Exolve-Buy.md) | buying-number (API) | Buy |
| [`raw/Exolve-Delete.html`](raw/Exolve-Delete.html) / [`.md`](raw/Exolve-Delete.md) | deleting-number | Delete |
| [`raw/Exolve-GetInfo.html`](raw/Exolve-GetInfo.html) / [`.md`](raw/Exolve-GetInfo.md) | purchased-number | GetInfo |
| [`raw/Exolve-GetPurchased.html`](raw/Exolve-GetPurchased.html) / [`.md`](raw/Exolve-GetPurchased.md) | getting-purchsed-numbers | Purchased list (docs) |
| [`raw/Exolve-SetAmdState.html`](raw/Exolve-SetAmdState.html) / [`.md`](raw/Exolve-SetAmdState.md) | setting-amd-state | SetAmdState |
| [`raw/Exolve-SetCallForwarding.html`](raw/Exolve-SetCallForwarding.html) / [`.md`](raw/Exolve-SetCallForwarding.md) | call-forwarding | SetCallForwarding |
| [`raw/Exolve-DeleteCallForwarding.html`](raw/Exolve-DeleteCallForwarding.html) / [`.md`](raw/Exolve-DeleteCallForwarding.md) | deleting-call-forwarding | DeleteCallForwarding |
| [`raw/Exolve-GetAttributes.html`](raw/Exolve-GetAttributes.html) / [`.md`](raw/Exolve-GetAttributes.md) | getting-number-attributes | GetAttributes |

## Note on GetFree examples

Every documented GetFree success example includes `category_id` and usually `random: true`, even though the param table marks them optional. Live canaries compare docs-shaped requests vs no-category probes before choosing sync mode. See also the buying-number instruction Postman example.

## Derived docs

- [`../exolve-contract.md`](../exolve-contract.md)
- [`../exolve-field-mapping.md`](../exolve-field-mapping.md)
- [`../exolve-implementation-notes.md`](../exolve-implementation-notes.md)
- Code: `backend/app/providers/exolve/contract.py`

## Rule

Saved artifacts under `exolve/raw/` are the method source of truth for Exolve. Derived contract/mapping must not invent methods or fields.

**Product integration is read-only:** `GetList` + `GetFree` only. Lock / Unlock / Buy / Delete / purchased inventory / forwarding / AMD are archived for reference and **out of scope**.

The short region table in the GetFree article is an excerpt — the full region set comes from GetList `regions[]`.
