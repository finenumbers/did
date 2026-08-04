# UIS documentation source

- Portal: [UIS Data API](https://www.uiscom.ru/academiya/spravochnyj-centr/dokumentatsiya-api/data_api/)
- Free inventory: [get.available_virtual_numbers](https://www.uiscom.ru/academiya/spravochnyj-centr/dokumentatsiya-api/data_api/vn/get_available_virtual_numbers/)
- Purchased (connected) inventory: [get.virtual_numbers](https://www.uiscom.ru/academiya/spravochnyj-centr/dokumentatsiya-api/data_api/vn/get_virtual_numbers/)
- Auth session: [login.user](https://www.uiscom.ru/academiya/spravochnyj-centr/dokumentatsiya-api/data_api/authentication/login_user)

## Artifacts

| File | Source page |
|---|---|
| [`raw/UIS-Data-API.html`](raw/UIS-Data-API.html) | Data API conventions (base URL, pagination, auth, errors) |
| [`raw/UIS-get-available-virtual-numbers.html`](raw/UIS-get-available-virtual-numbers.html) | Free / available VN |
| [`raw/UIS-get-virtual-numbers.html`](raw/UIS-get-virtual-numbers.html) | Connected / purchased VN |
| [`raw/UIS-login-user.html`](raw/UIS-login-user.html) | login.user |

## Rule

Saved HTML under `uis/raw/` is the method source of truth for UIS. Derived `uis-contract.md` / `uis-field-mapping.md` must not invent methods or fields. Integration is **read-only** (`get.*` with ЛК `access_token` only; `login.user` documented but unused by product).
