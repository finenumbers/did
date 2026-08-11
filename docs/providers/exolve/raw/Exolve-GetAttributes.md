Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-number-attributes/
Title: Метод GetAttributes | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- GetAttributes

# GetAttributes

## 
 Метод GetAttributes

Примените метод GetAttributes для получения информации о настройках купленного номера (переадресация входящих звонков, запись разговоров).

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/GetAttributes
`
```

### 
 Авторизация

Передайте следующие заголовки HTTP для успешной авторизации.
|  Имя | Тип | Описание |
|  Authorization | string | API-ключ приложения с `Bearer` перед ним. Пример: `Bearer e***s0`, где `e***s0` замените на API-ключ вашего приложения |

### 
 Входные параметры

Передайте следующие параметры в теле запроса в JSON-формате. Параметры, отмеченные жирным шрифтом, являются обязательными.
|  Параметр | Тип | Описание |
|  number_code | uint64 | код номера |

### 
 Выходные параметры

|  Параметр | Тип | Описание |
|  number_resource_id | uint64 | код номера |
|  status_name | string | статус номера |
|  attributes | NumberAttributes | атрибуты номера, информация о настройке |

#### 
 NumberAttributes

|  Параметр | Тип | Описание |
|  call_record | boolean | запись звонков. `True` — подключено, `False` — отключено |
|  call_forwarding_type | enum ForwardingType | тип переадресации входящих звонков |
|  call_forwarding_sip | enum ForwardingSip | внешний SIP ID, на который переадресуются входящие звонки |
|  call_forwarding_number | enum ForwardingNumber | настройки номера или SIP ID, на который переадресуются входящие звонки |
|  call_forwarding_ipcr | enum ForwardingIpcr | URL, на который переадресуются входящие звонки |
|  call_transcribation | boolean | текстовая расшифровка звонков. `True` — подключено, `False` — отключено |
|  incoming_sms_enabled | boolean | получение входящих SMS. `True` — подключено, `False` — отключено |
|  speech_analytics | boolean | речевая аналитика звонков. `True` — подключено, `False` — отключено |
|  amd | boolean | детектирование автоинформаторов. `True` — подключено, `False` — отключено |

На всех новых номерах автоматически подключена запись разговора. Отключить её можно на 31-й день с момента покупки. Изменение срока хранения записей доступно в настройках приложения в Личном кабинете.

Речевая аналитика уже включает в себя текстовую расшифровку звонка, поэтому подключить одновременно и аналитику, и транскрибацию нельзя — выберите одну из услуг

#### 
 ForwardingType

|  Параметр | Тип | Описание |
|  0 | string | тип переадресации не определён |
|  1 | string | переадресация на внешний SIP-аккаунт |
|  2 | string | переадресация на номер или SIP ID платформы |
|  3 | string | динамическая переадресация по API |
|  4 | string | переадресация на Static IP |

#### 
 ForwardingNumber

|  Параметр | Тип | Описание |
|  redirect_type | int64 | тип переадресации: 1 - одиночная, 2 - последовательная, 3 - параллельная |
|  call_control | CallControl | управление входящим вызовом |
|  event_url | string | URL для отправки уведомлений о ходе звонка |
|  event_extended | boolean | `True` для получения расширенных уведомлений. `False` для получения стандартного набора уведомлений |
|  file_to_a | string | аудиосообщение звонящему абоненту |
|  file_to_b | string | аудиосообщение принимающему абоненту |
|  answer | boolean | `True` для проигрывания аудиосообщения в предответном состоянии. `False` для проигрывания аудиосообщения в ответном состоянии (`False` по умолчанию) |
|  masking | boolean | `True` для скрытия номер звонящего абонента. `False` для показа оригинального номера звонящего абонента |
|  display_number | string | номер Exolve, который видит звонящий абоненту при вызове |

#### 
 CallControl

|  Параметр | Тип | Описание |
|  period | string | период переадресации входящего вызова |
|  period_description | string | описание периода переадресации вызова |
|  timeout | uint32 | время ожидания ответа в секундах |
|  active | boolean | `True` для переадресации вызова на `redirect_number`, `False` для сброса вызова |
|  name | string | символьное имя номера для переадресации вызова |
|  redirect_number | string | номер для переадресации |
|  dtmf | string | добавочный номер |

#### 
 ForwardingIpcr

|  Параметр | Тип | Описание |
|  url | string | URL, на который происходит переадресация |
|  reserve | string | номер, на который происходит переадресация, если URL не доступен |

#### 
 ForwardingSip

|  Параметр | Тип | Описание |
|  sip_uri | string | URI SIP-аккаунта, на который переадресуются входящие звонки |

### 
 Примеры

Входные параметры:

```
`{
"number_code": 74996487174}
`
```

Выходные параметры для номера с переадресацией на номер:

```
`{
"number_resource_id": "94004",
"status_name": "Active",
"attributes": {
"call_record": false,
"call_forwarding_type": 2,
"call_forwarding_number": {
"redirect_type": 1,
"call_control":[
 {
"timeout": "16",
"active": true,
"name": "звонит клиент",
"redirect_number": "74996480184",
"dtmf": "8" }
 ],
"event_url": "https://example.com/",
"event_extended": true,
"file_to_a": "12345",
"file_to_b": "54321",
"answer": true,
"masking": true,
"display_number": "74995557890" }
 }
}
`
```

Входные параметры для динамической переадресации по API:

```
`{
"number_resource_id": "51802",
"status_name": "",
"attributes": {
"call_record": true,
"call_forwarding_type": 3,
"call_forwarding_ipcr": {
"url": "http://example.com",
"reserve": "74996482846" }
 }
}
`
```

### 
 Возможные ошибки

|  Код | Статус | Пример сообщения | Описание |
|  400 | Bad Request | proto: syntax error (line 2:20): invalid value п | значение в поле `number_code` не валидно |
|  400 | Bad Request | proto: (line 3:1): invalid value for uint64 type: } | не задано значение в поле `number_code` |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
