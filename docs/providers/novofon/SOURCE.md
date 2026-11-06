# Novofon documentation source

- Portal: [Novofon Data API](https://novofon.github.io/data_api/)
- Free inventory: [get.available_virtual_numbers](https://novofon.github.io/data_api/vn/get_available_virtual_numbers/)
- Purchased (connected) inventory: [get.virtual_numbers](https://novofon.github.io/data_api/vn/get_virtual_numbers/)
- Auth session (documented, unused): [login.user](https://novofon.github.io/data_api/authentication/login_user/)
- Client account: [get.account](https://novofon.github.io/data_api/account/get_account/)
- Agent customer users: [get.customer_users](https://novofon.github.io/data_api/partner/get_customer_users/)
- Order shop and owned list (classic User API, not Data API): [novofon/user-api-v1](https://github.com/novofon/user-api-v1) and the Zadarma numbers instruction. `GET /v1/direct_numbers/countries/`, `/country/`, `/available/<DIRECTION_ID>/`, and `GET /v1/direct_numbers/` on `https://api.novofon.com`

## Artifacts

| File | Source page |
|---|---|
| [`raw/Novofon-Data-API.html`](raw/Novofon-Data-API.html) | Data API conventions (base URL, pagination, auth, errors) |
| [`raw/Novofon-vn.html`](raw/Novofon-vn.html) | Virtual-number method index |
| [`raw/Novofon-get-available-virtual-numbers.html`](raw/Novofon-get-available-virtual-numbers.html) | Free / available VN |
| [`raw/Novofon-get-virtual-numbers.html`](raw/Novofon-get-virtual-numbers.html) | Connected / purchased VN |
| [`raw/Novofon-login-user.html`](raw/Novofon-login-user.html) | login.user |
| [`raw/Novofon-get-account.html`](raw/Novofon-get-account.html) | get.account |
| [`raw/Novofon-get-customer-users.html`](raw/Novofon-get-customer-users.html) | get.customer_users |

## Derived docs

- [`../novofon-contract.md`](../novofon-contract.md)
- [`../novofon-field-mapping.md`](../novofon-field-mapping.md)
- [`../novofon-implementation-notes.md`](../novofon-implementation-notes.md)
- Code: `backend/app/providers/novofon/contract.py`

## Rule

Saved HTML under `novofon/raw/` is the method source of truth for the Data API. The order shop and the owned list are the classic User API above; example payloads in the contract are field sketches, not inventory. The Novofon 2.0 API screen issues one key and does not show Key or Secret, so those calls are made only when `api_key` is set. Integration is **read-only**: classify the token, read `get.available_virtual_numbers` and `get.virtual_numbers`, then GET every country's shop and `GET /v1/direct_numbers/` only when Key is present. `login.user`, `order`, and `prolong` are not called. HTTP 501 on `/country/` refuses the free slice and writes nothing.
