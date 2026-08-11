# MCN Информация о номерах (NNP/MNP) OpenAPI extract

Base: https://paidmethods.mcn.ru

## Paths

### POST `/api/protected/api/link/add`

- summary: Link shortening API
- operationId: _api/protected/api/link/add

### GET `/api/protected/api/mnp/numberInfo`

- summary: mnp
- operationId: _api/protected/api/mnp/numberInfo
- parameters:
  - `number` (query, required=True, type=string, default=None)

### GET `/api/protected/api/nnp/getCities`

- summary: Geographical information about cities in a given country
- operationId: _api/protected/api/nnp/getCities
- parameters:
  - `city_id` (query, required=False, type=number, default=None)
  - `country_code` (query, required=False, type=number, default=None)
  - `region_id` (query, required=False, type=number, default=None)

### GET `/api/protected/api/nnp/getNumberRanges`

- summary: Number ranges (from, to) information
- operationId: _api/protected/api/nnp/getNumberRanges
- parameters:
  - `country_code` (query, required=False, type=number, default=None)
  - `ndc` (query, required=False, type=number, default=None)
  - `ndc_type_id` (query, required=False, type=number, default=None)
  - `is_active` (query, required=False, type=boolean, default=None)
  - `operator_id` (query, required=False, type=number, default=None)
  - `region_id` (query, required=False, type=number, default=None)
  - `city_id` (query, required=False, type=number, default=None)
  - `number_full` (query, required=False, type=string, default=None)
  - `number` (query, required=False, type=string, default=None)
  - `limit` (query, required=False, type=number, default=None)
  - `offset` (query, required=False, type=number, default=None)

### GET `/api/protected/api/nnp/getOperators`

- summary: Operators in a given country
- operationId: _api/protected/api/nnp/getOperators
- parameters:
  - `operator_id` (query, required=False, type=number, default=None)
  - `country_code` (query, required=False, type=number, default=None)

### GET `/api/protected/api/nnp/numberInfo`

- summary: Number information (geo, ndc type, operator)
- operationId: _api/protected/api/nnp/numberInfo
- parameters:
  - `number` (query, required=True, type=string, default=None)
  - `isArray` (query, required=False, type=boolean, default=None)
