# Voximplant documentation source

- Portal: [Voximplant Docs](https://docs.voximplant.ai/)
- Management API auth: [Authorization](https://docs.voximplant.ai/api-reference/management-api/authorization)
- Errors: [Errors](https://docs.voximplant.ai/api-reference/management-api/errors)
- Account: [GetAccountInfo](https://docs.voximplant.ai/api-reference/management-api/reference/accounts/get-account-info)
- Phone numbers index: [Phone Numbers](https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers)

## Artifacts

Saved under [`raw/`](raw/). Prefer HTML as verbatim page capture; `.md` is a searchable extract.

### Product-used (read-only integration)

| File | Source page | Product use |
|---|---|---|
| [`raw/Voximplant-Authorization.html`](raw/Voximplant-Authorization.html) / [`.md`](raw/Voximplant-Authorization.md) | Service account JWT | Settings auth |
| [`raw/Voximplant-Errors.html`](raw/Voximplant-Errors.html) / [`.md`](raw/Voximplant-Errors.md) | Error codes | Client error envelope |
| [`raw/Voximplant-GetAccountInfo.html`](raw/Voximplant-GetAccountInfo.html) / [`.md`](raw/Voximplant-GetAccountInfo.md) | GetAccountInfo | Test connection, currency, `api_address` |
| [`raw/Voximplant-GetPhoneNumberCategories.html`](raw/Voximplant-GetPhoneNumberCategories.html) / [`.md`](raw/Voximplant-GetPhoneNumberCategories.md) | Categories | RU category discovery |
| [`raw/Voximplant-GetPhoneNumberRegions.html`](raw/Voximplant-GetPhoneNumberRegions.html) / [`.md`](raw/Voximplant-GetPhoneNumberRegions.md) | Regions + prices | Dictionaries + free slice plan |
| [`raw/Voximplant-GetNewPhoneNumbers.html`](raw/Voximplant-GetNewPhoneNumbers.html) / [`.md`](raw/Voximplant-GetNewPhoneNumbers.md) | Free inventory | **Sync all free RU numbers** |

### Archived for reference (out of product scope)

| File | Source page | Method |
|---|---|---|
| [`raw/Voximplant-GetPhoneNumberCountryStates.html`](raw/Voximplant-GetPhoneNumberCountryStates.html) / [`.md`](raw/Voximplant-GetPhoneNumberCountryStates.md) | Country states | Not needed for RU |
| [`raw/Voximplant-GetPhoneNumbers.html`](raw/Voximplant-GetPhoneNumbers.html) / [`.md`](raw/Voximplant-GetPhoneNumbers.md) | Account phones | Purchased list (OOS v1) |
| [`raw/Voximplant-AttachPhoneNumber.html`](raw/Voximplant-AttachPhoneNumber.html) / [`.md`](raw/Voximplant-AttachPhoneNumber.md) | Attach / buy | Mutation — never call |

## Derived docs

- [`../voximplant-contract.md`](../voximplant-contract.md)
- [`../voximplant-field-mapping.md`](../voximplant-field-mapping.md)
- [`../voximplant-implementation-notes.md`](../voximplant-implementation-notes.md)
- Code: `backend/app/providers/voximplant/contract.py`

## Rule

Saved artifacts under `voximplant/raw/` are the method source of truth for Voximplant. Derived contract/mapping must not invent methods or fields.

**Product integration is read-only:** Authorization + GetAccountInfo + GetPhoneNumberCategories + GetPhoneNumberRegions + GetNewPhoneNumbers. Attach / purchased inventory are archived and **out of scope**.

**RU-only completeness:** sync must load **all** free Russian numbers (every listable RU category × every stock region × full `total_count` pagination).
