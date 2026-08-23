# Twilio — source of truth

## Portal

- Phone Numbers API: https://www.twilio.com/docs/phone-numbers/api
- AvailablePhoneNumbers: https://www.twilio.com/docs/phone-numbers/api/availablephonenumber-resource
- Local / TollFree / Mobile search: https://www.twilio.com/docs/phone-numbers/api/availablephonenumberlocal-resource
- Pricing Phone Numbers: https://www.twilio.com/docs/phone-numbers/pricing
- OpenAPI: https://github.com/twilio/twilio-oai (`twilio_api_v2010.json`)
- Production API: `https://api.twilio.com/2010-04-01`
- Pricing API: `https://pricing.twilio.com/v1`

## Raw archive

No `raw/` folder: vendor HTML was not uploaded to the repo. Source of truth is the
online documentation above **plus** `backend/app/providers/twilio/contract.py`.

## Derived artifacts

| Artifact | Path |
|---|---|
| Machine contract | [`twilio-contract.md`](../twilio-contract.md) |
| Field mapping | [`twilio-field-mapping.md`](../twilio-field-mapping.md) |
| Implementation notes | [`twilio-implementation-notes.md`](../twilio-implementation-notes.md) |
| Code mirror | `backend/app/providers/twilio/contract.py` |

## Scope rule

Twilio is **not** part of the RU free-numbers catalog. It feeds its own section
(«Номера Twilio», `/twilio`) backed by `twilio_catalog` (country × type) and
`twilio_available_numbers` (sample E.164). It never writes to
`numbers_catalog_normalized`. Integration is **read-only**: GET only. Never call
`POST IncomingPhoneNumbers` or Global Catalog preview purchase.
