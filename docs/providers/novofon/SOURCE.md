# Novofon documentation source

- Portal: [Novofon Data API](https://novofon.github.io/data_api/)
- Free inventory: [get.available_virtual_numbers](https://novofon.github.io/data_api/vn/get_available_virtual_numbers/)
- Purchased (connected) inventory: [get.virtual_numbers](https://novofon.github.io/data_api/vn/get_virtual_numbers/)
- Auth session (documented, unused): [login.user](https://novofon.github.io/data_api/authentication/login_user/)
- Client account: [get.account](https://novofon.github.io/data_api/account/get_account/)
- Agent customer users: [get.customer_users](https://novofon.github.io/data_api/partner/get_customer_users/)

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

Saved HTML under `novofon/raw/` is the method source of truth for Novofon. Derived contract/mapping must not invent methods or fields. Integration is **read-only**: `get.customer_users` and `get.account` classify the token, then `get.available_virtual_numbers` and `get.virtual_numbers`. `login.user` is documented but unused.
