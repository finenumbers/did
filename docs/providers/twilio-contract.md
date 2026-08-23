# Twilio — machine contract

Nav: [`twilio/SOURCE.md`](twilio/SOURCE.md) · [`twilio-field-mapping.md`](twilio-field-mapping.md) · [`twilio-implementation-notes.md`](twilio-implementation-notes.md) · code `backend/app/providers/twilio/contract.py`

## Auth

- `auth_settings.account_sid` + `auth_settings.auth_token`.
- HTTP Basic: username = Account SID, password = Auth Token.
- Account SID is also in the URL path `/2010-04-01/Accounts/{AccountSid}/…`.
- Default base URL `https://api.twilio.com/2010-04-01`.
- Pricing host is separate: `https://pricing.twilio.com/v1` (`extra_settings.pricing_base_url` override only).

## Read-only boundary

Allowed (GET only):

| Method | Notes |
|---|---|
| `GET /Accounts/{Sid}/AvailablePhoneNumbers.json` | Paginated countries list. Connection probe. |
| `GET /Accounts/{Sid}/AvailablePhoneNumbers/{CC}.json` | One country + `subresource_uris`. |
| `GET /Accounts/{Sid}/AvailablePhoneNumbers/{CC}/{Local\|Mobile\|TollFree\|Voip\|National\|SharedCost\|MachineToMachine}.json` | Live search only, never persisted. |
| `GET https://pricing.twilio.com/v1/PhoneNumbers/Countries/{ISO}` | Monthly price by type. |

Never call: `POST/PATCH/DELETE IncomingPhoneNumbers`, ActiveNumbers, Global Catalog preview, Voice Pricing (outbound prefixes are call rates, not inventory).

## Grain

One catalog row = **country + type** from live `subresource_uris` keys. Not E.164, not city, not area code.

Types come only from keys that actually appear on the country. Official HTML documents Local / TollFree / Mobile; OpenAPI also has National / Voip / SharedCost / MachineToMachine.

## Missing dictionaries (verified)

- No `GET …/Regions`, `…/Cities`, `…/AreaCodes`, `…/Prefixes`.
- Country object has ISO `country_code`, not E.164 calling code.
- `InRegion` / `AreaCode` / `InLocality` / `Contains` are search filters the client already knows.
- Voice Pricing `destination_prefixes` are outbound minute rates — out of scope.

## Available numbers search

- Typical ceiling ~30 numbers; not a dump; `Page`/`PageToken` do not walk inventory.
- Live endpoint only. Empty result means this sample is empty, not «no coverage».
- Do not pass `Beta` (vendor default `true` includes beta numbers).

## Pricing

- `number_type`: `local`, `mobile`, `national`, `toll free`.
- Catalog maps `toll_free` → `toll free`. voip / shared_cost / machine_to_machine stay unpriced (empty, not 0).
- No setup / NRC in GA Pricing.

## Pagination and limits

- Countries list: follow `next_page_url` / `next_page_uri`, `PageSize` up to 1000.
- Twilio 429 is a **concurrency** limit (`Twilio-Concurrent-Requests`), not DIDWW-style rps. Client is sequential with backoff and honours `Retry-After`.
