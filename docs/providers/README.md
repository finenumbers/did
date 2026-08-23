# Provider documentation artifacts

## Стандарт комплекта

Для каждого источника нумерации в репозитории должен быть **одинаковый набор артефактов** (глубина содержимого может отличаться — важна навигация, не длина файлов):

| Артефакт | Назначение |
|---|---|
| `{name}/SOURCE.md` | Портал/URL, индекс `raw/`, правило SoT, путь к `contract.py` |
| `{name}/raw/` | Архив vendor-материалов (если есть; не создавать пустую папку ради симметрии) |
| `{name}-contract.md` | Machine contract: auth, read-only boundary, methods, paging/completeness |
| `{name}-field-mapping.md` | API / feed → catalog / raw tables |
| `{name}-implementation-notes.md` | Operational quirks из кода: Settings, stages, wipe, live TODOs |
| `backend/app/providers/{name}/contract.py` | Код-зеркало contract (константы путей/лимитов) |

Правила:

1. Uploaded `raw/` (или явный code-SoT для Finenumbers) побеждает память и интернет.
2. Derived docs **не изобретают** методы/поля сверх источников. Маркеры: `VERIFIED` / `EXAMPLE-CONFIRMED` / `UNVERIFIED` / `OPERATIONAL`.
3. Integrations are **read-only**.
4. `implementation-notes` не дублируют method tables из contract — только operational.

## Source of truth (индекс)

- **SipOut:** [`sipout/SOURCE.md`](sipout/SOURCE.md), [`sipout-contract.md`](sipout-contract.md), [`sipout-field-mapping.md`](sipout-field-mapping.md), [`sipout-implementation-notes.md`](sipout-implementation-notes.md); raw [`sipout/raw/`](sipout/raw/); code `backend/app/providers/sipout/contract.py`
- **Runexis:** [`runexis/SOURCE.md`](runexis/SOURCE.md) (DIDAPI + Numbering), [`runexis-contract.md`](runexis-contract.md), [`runexis-numbering-api-contract.md`](runexis-numbering-api-contract.md), [`runexis-field-mapping.md`](runexis-field-mapping.md), [`runexis-implementation-notes.md`](runexis-implementation-notes.md); raw [`runexis/raw/`](runexis/raw/); code `backend/app/providers/runexis/contract.py`
- **Finenumbers / PSTN:** [`finenumbers/SOURCE.md`](finenumbers/SOURCE.md), [`finenumbers-contract.md`](finenumbers-contract.md), [`finenumbers-field-mapping.md`](finenumbers-field-mapping.md), [`finenumbers-implementation-notes.md`](finenumbers-implementation-notes.md); vendor HTML **не** в репо (SoT = code + live API); code `backend/app/providers/finenumbers/contract.py`
- **UIS Data API:** [`uis/SOURCE.md`](uis/SOURCE.md), [`uis-contract.md`](uis-contract.md), [`uis-field-mapping.md`](uis-field-mapping.md), [`uis-implementation-notes.md`](uis-implementation-notes.md); raw [`uis/raw/`](uis/raw/); code `backend/app/providers/uis/contract.py`
- **Aurora Telecom:** [`aurora/SOURCE.md`](aurora/SOURCE.md), [`aurora-contract.md`](aurora-contract.md), [`aurora-field-mapping.md`](aurora-field-mapping.md), [`aurora-implementation-notes.md`](aurora-implementation-notes.md); sample [`aurora/raw/`](aurora/raw/); code `backend/app/providers/aurora/contract.py`
- **Exolve (МТС Exolve):** [`exolve/SOURCE.md`](exolve/SOURCE.md), [`exolve-contract.md`](exolve-contract.md), [`exolve-field-mapping.md`](exolve-field-mapping.md), [`exolve-implementation-notes.md`](exolve-implementation-notes.md); raw [`exolve/raw/`](exolve/raw/); code `backend/app/providers/exolve/contract.py`
- **Voximplant:** [`voximplant/SOURCE.md`](voximplant/SOURCE.md), [`voximplant-contract.md`](voximplant-contract.md), [`voximplant-field-mapping.md`](voximplant-field-mapping.md), [`voximplant-implementation-notes.md`](voximplant-implementation-notes.md); raw [`voximplant/raw/`](voximplant/raw/); code `backend/app/providers/voximplant/contract.py`
- **MCN Telecom:** [`mcn/SOURCE.md`](mcn/SOURCE.md), [`mcn-contract.md`](mcn-contract.md), [`mcn-field-mapping.md`](mcn-field-mapping.md), [`mcn-implementation-notes.md`](mcn-implementation-notes.md); raw [`mcn/raw/`](mcn/raw/) (Витрина = free stock; NNP archived as non-inventory); code `backend/app/providers/mcn/contract.py`
- **DIDWW:** [`didww/SOURCE.md`](didww/SOURCE.md), [`didww-contract.md`](didww-contract.md), [`didww-field-mapping.md`](didww-field-mapping.md), [`didww-implementation-notes.md`](didww-implementation-notes.md); vendor HTML **не** в репо (SoT = online docs + code); отдельный раздел «Номера DIDWW», вне общего прогона РФ; code `backend/app/providers/didww/contract.py`
- **Twilio:** [`twilio/SOURCE.md`](twilio/SOURCE.md), [`twilio-contract.md`](twilio-contract.md), [`twilio-field-mapping.md`](twilio-field-mapping.md), [`twilio-implementation-notes.md`](twilio-implementation-notes.md); отдельный раздел «Номера Twilio», выборка E.164 не полный инвентарь; code `backend/app/providers/twilio/contract.py`

## Markers

| Marker | Meaning |
|---|---|
| VERIFIED | Explicitly described in formal docs prose/param tables |
| EXAMPLE-CONFIRMED | Appears only in example JSON |
| UNVERIFIED | Not confirmed — isolate, mark `TODO: VERIFY_WITH_DOC_FILE`, keep raw |
| OPERATIONAL | Product/code behavior not claimed as vendor prose |

## Strict mode

If documentation is insufficient: isolate uncertainty, keep `raw_payload`, stop short of unsafe assumptions. Provider integrations are **read-only**.
