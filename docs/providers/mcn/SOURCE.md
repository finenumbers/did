# MCN Telecom documentation source

- Public API catalog: [apidocs.mcn.ru](https://apidocs.mcn.ru/)
- **Витрина (free inventory):** OpenAPI via [project 31 docs](https://apidocs.mcn.ru/api/projects/31/docs) → `shop.mcn.ru`
- **Информация о номерах (NNP/MNP lookup — not free stock):** [project 26](https://apidocs.mcn.ru/api/projects/26/docs) → `paidmethods.mcn.ru`
- Token help: [Как получить токен](https://help.mcn.ru/ru-RU/support/solutions/articles/43000715053)
- Base API index (mentions `getFreeNumbers`, no public schema): [Методы API → Base](https://help.mcn.ru/ru-RU/support/solutions/articles/43000737563)

## Artifacts

Saved under [`raw/`](raw/).

### Product-used (read-only integration)

| File | Source | Product use |
|---|---|---|
| [`raw/MCN-Vitrina-openapi.json`](raw/MCN-Vitrina-openapi.json) | shop.mcn.ru OpenAPI | **Source of truth** for showcase methods |
| [`raw/MCN-Vitrina.md`](raw/MCN-Vitrina.md) / [`.html`](raw/MCN-Vitrina.html) | Extract of paths/schemas | Searchable contract |
| [`raw/MCN-token-help.md`](raw/MCN-token-help.md) / [`.html`](raw/MCN-token-help.html) | LK Integrations → Tokens | Settings auth |
| [`raw/MCN-Vitrina-project.json`](raw/MCN-Vitrina-project.json) | apidocs project metadata | Index |

### Archived for reference (out of product scope / non-inventory)

| File | Source | Notes |
|---|---|---|
| [`raw/MCN-NNP-openapi.json`](raw/MCN-NNP-openapi.json) + md/html | Информация о номерах | NNP/MNP lookup only — **not** free DID stock |
| [`raw/MCN-base-api-help.md`](raw/MCN-base-api-help.md) / html | Base API help | Mentions `POST …/account/getFreeNumbers` without schema — not v1 primary |

## Rule

Derived `mcn-contract.md` / `mcn-field-mapping.md` must not invent fields beyond archived OpenAPI.

**Product integration is read-only Витрина:** countries / regions / cities / numbers. Checkout/buy and NNP are out of scope for inventory sync.

**Completeness:** sync must load **all** free RU numbers (`countryCode=643`) across regions/cities with prices, paging to `totalNumbers`.
