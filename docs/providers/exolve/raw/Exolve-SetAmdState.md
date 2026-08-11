Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/setting-amd-state/
Title: Метод SetAmdState | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- SetAmdState

# SetAmdState

## 
 Метод SetAmdState

Примените метод SetAmdState для подключения и отключения услуги детектирования автоответчика при исходящих звонках.

Услуга подключается бесплатно. Плата списывается с баланса аккаунта за каждый звонок, разорванный из-за обнаруженного автоответчика

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/SetAmdState
`
```

### 
 Авторизация

Передайте следующие Заголовки HTTP для успешной авторизации.
|  Имя | Тип | Описание |
|  Authorization | string | API-ключ приложения с `Bearer` перед ним. Пример: `Bearer e***s0`, где `e***s0` замените на API-ключ вашего приложения |

### 
 Входные параметры

Передайте следующие параметры в теле запроса в JSON-формате. Параметры, отмеченные жирным шрифтом, являются обязательными.
|  Параметр | Тип | Описание |
|  number_code | uint64 | купленный номер |
|  amd | boolean | `True` для включения детектора. `False` для отключения детектора |

Примечание

Чтобы включить услугу детектирования автоответчиков на номере, убедитесь, что услуга уже подключена в настройках этого приложения в Личном кабинете разработчика

### 
 Выходные параметры

Пустой JSON с 200 OK статусом.

### 
 Примеры

Входные параметры:

```
`{
"number_code": 79991112233,
"amd": true}
`
```

Выходные параметры:

```
`{}
`
```

### 
 Возможные ошибки

|  Код | Статус | Пример сообщения | Описание |
|  400 | Bad Request | “unknown field ‘*’” |  |
|  400 | Bad Request | “unexpected token *” |  |
|  400 | Bad Request | “invalid value *” | невалидный формат данных |
|  400 | Bad Request | “invalid SetAmdStateRequest.NumberCode: value must be greater than 0” | не указан номер, на котором нужно подключить услугу |
|  400 | Bad Request | “invalid value for uint64 field numberCode: ‘*’” | невалидный формат номера |
|  400 | Bad Request | “invalid value for bool field amd: *” | невалидный формат данных |
|  400 | Bad Request | “Error setting amd: amd already disabled on number” | услуга уже отключена на номере |
|  400 | Bad Request | “Error setting amd: number is missing in the application” | номер не принадлежит указанному приложению |
|  401 | Unauthorized | Unauthorized | невалидный API-ключ |
|  401 | Unauthorized | malformed token | отсутствует API-ключ |
|  403 | Forbidden | “Error setting amd: activate amd service on this application” | услугу детектирования сначала нужно подключить в настройках приложения |
|  404 | Bad Request |  | некорректно введён URL запроса |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
