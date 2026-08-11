Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-purchsed-numbers/
Title: Метод GetList (купленные номера) | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- GetList (купленные номера)

# GetList (купленные номера)

## 
 Метод GetList

Примените метод GetList для получения списка ваших купленных номеров.

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/customer/v1/GetList
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
|  application_uuid | string | идентификатор приложения, номера которого нужно найти |
|  type_name | string | тип номера |
|  category_id | uint64 | категория номера |
|  region_id | uint64 | регион номера |
|  date_from | string | дата покупки номера в формате RFC-3339 / ISO-8601, от которой начинать выборку |
|  date_to | string | дата покупки номера в формате RFC-3339 / ISO-8601, до которой продолжать выборку |
|  search_filter | string | фильтр поиска по номеру |
|  limit | uint64 | лимит выводимых строк |
|  offset | uint64 | номер строки, с которой начинать выборку (начинается с 0) |
|  sip_filter | enum SipFilter | наличие или отсуствие привязанного к номеру SIP-соединения |

#### 
 Список типов номеров (type_id)

|  Параметр | ID типа | Описание |
|  DEF | 1104 | Мобильный |
|  ABC | 1105 | Городской |
|  KDU | 1106 | Федеральный 8-800 (использовать только с регионом Россия) |

#### 
 Список категорий номеров (category_id)

|  Название | ID категории номера для типа мобильный | ID категории номера для типа городской | ID категории номера для типа 7-800 |
|  Обычный | 10000 | 10001 | 10002 |
|  Бронзовый | 10010 | 10011 | 10012 |
|  Серебряный | 10020 | 10021 | 10022 |
|  Золотой | 10030 | 10031 | 10032 |
|  Платиновый | 10040 | 10041 | 10042 |
|  Эксклюзивный | 10050 | 10051 | 10052 |

#### 
 Список регионов (region_id)

|  Название | ID типа номера |
|  Россия | 10084 |
|  Магнитогорск | 10186 |
|  Пермь | 10181 |
|  Санкт-Петербург | 10182 |
|  Москва | 10230 |
|  Ростов-на-Дону | 10231 |
|  Омск | 10196 |
|  Новороссийск | 10221 |
|  Екатеринбург | 10190 |
|  Казань | 10195 |
|  Сочи | 10153 |
|  Самара | 10192 |
|  Краснодар | 10184 |
|  Нижний Новгород | 10189 |
|  Новосибирск | 10183 |
|  Красноярск | 10191 |
|  Челябинск | 10229 |
|  Тольятти | 10227 |
|  Воронеж | 10193 |

#### 
 SipFilter

|  Параметр | Тип | Описание |
|  0 | enum | фильтр по SIP-соединениям не применяется |
|  1 | enum | нет привязанного SIP-соединения |
|  2 | enum | есть привязанное SIP-соединение |

### 
 Выходные параметры

|  Параметр | Тип | Описание |
|  numbers | array NumberElement | список номеров с информацией по ним |
|  total | uint32 | общее количество купленных номеров |

#### 
 NumberElement

|  Параметр | Тип | Описание |
|  application_uuid | string | идентификатор приложения, в котором куплен номер |
|  application_name | string | название приложения, в котором куплен номер |
|  number_name | string | номер |
|  description | string | описание |
|  type_name | string | тип |
|  region_name | string | регион |
|  subscription_fee | string | ежемесячная абонентская плата |
|  install_fee | string | единоразовая плата за подключение |
|  create_date | string | дата покупки номера в формате RFC-3339 / ISO-8601 |
|  category_name | string | название категории |
|  number_options | array NumberOptions | возможности номера (звонки, SMS) |
|  call_forwarding_flag | bool | переадресация входящих звонков с этого номера на другой ресурс (доступно, только если во входных параметрах передан application_uuid), `True` — подключено, `False` — отключено |
|  call_forwarding_number | array CallForwardingNumber | настройки переадресации с этого номера на другой номер (доступно, только если `call_forwarding_flag: true`) |
|  call_forwarding_sip | array CallForwardingSip | настройки переадресации с этого номера на внешний SIP-аккаунт (доступно, только если `call_forwarding_flag: true`) |
|  call_forwarding_ip_static | array CallForwardingStaticIP | настройки переадресации с этого номера на Static IP (доступно, только если `call_forwarding_flag: true`) |
|  call_forwarding_ipcr | array CallForwardingIpcr | настройки динамической переадресации с этого номера на другие ресурсы (доступно, только если `call_forwarding_flag: true`) |
 NumberOptions

|  Параметр | Тип | Описание |
|  incoming_calls | bool | входящие звонки, `True` — доступно, `False` — доступно |
|  outgoing_calls | bool | исходящие звонки, `True` — доступно, `False` — доступно |
|  incoming_sms | bool | входящие SMS, `True` — доступно, `False` — доступно |
|  outgoing_sms | bool | исходящие SMS, `True` — доступно, `False` — доступно |
 CallForwardingNumber

|  Параметр | Тип | Описание |
|  redirect_type | enum | 1 — одиночная, 2 — последовательная, 3 — параллельная |
|  redirect_number | string | номер, на который переадресуются входящие звонки |
 CallForwardingSip

|  Параметр | Тип | Описание |
|  sip_uri | string | URI внешнего SIP-аккаунта |
 CallForwardingStaticIP

|  Параметр | Тип | Описание |
|  did_name | uint64 | определяемый номер, который видит принимающий абонент |
|  ip | string | IP-адреса ресурса Static IP |
|  port | uint32 | порт IP-адреса |
|  timeout | uint32 | время ожидания ответа в секундах |
 CallForwardingIpcr

|  Параметр | Тип | Описание |
|  url | string | URL-адрес вашего сервера, от которого получаем инструкции по переадресации |
|  reserve | string | резервный номер — на него переадресуются входящие звонки, если URL сервера недоступен |

### 
 Примеры

Входные параметры:

```
`{
"application_uuid": "05f28d32-3cef-4bb5-9164-424e954aefb1",
"date_from": "2022-10-01T08:49:28.446495Z",
"date_to":"2025-05-22T08:49:28.446495Z",
"limit": 10,
"offset": 0}
`
```

Выходные параметры:

```
`{
"numbers": [
 {
"number_name": "79991234455",
"type_name": "DEF",
"region_name": "St. Petersburg",
"application_name": "для массовых рассылок и обзвона",
"subscription_fee": 150,
"install_fee": 590,
"create_date": "2025-05-28T13:53:26.711071Z",
"application_uuid": "05f28d32-3cef-4bb5-9164-424e954aefb1",
"call_forwarding_flag": true,
"number_options": {
"incoming_calls": true,
"outgoing_calls": true,
"incoming_sms": true,
"outgoing_sms": true },
"call_forwarding_number": {
"redirect_type": "1",
"redirect_number": "883140005577220" }
 },
 {
"number_name": "79991234466",
"type_name": "DEF",
"region_name": "Moscow",
"application_name": "для массовых рассылок и обзвона",
"subscription_fee": 150,
"install_fee": 590,
"create_date": "2025-05-27T11:51:43.850034Z",
"application_uuid": "05f28d32-3cef-4bb5-9164-424e954aefb1",
"call_forwarding_flag": true,
"number_options": {
"incoming_calls": true,
"outgoing_calls": true,
"incoming_sms": true,
"outgoing_sms": true },
"call_forwarding_ip_static": {
"did_name": "79991234477",
"ip": "111.112.113.114",
"port": 5060,
"timeout": 60 }
 }
 ],
"total": 2}
`
```

### 
 Возможные ошибки

|  Код | Статус | Пример сообщения | Описание |
|  400 | Bad Request | “error”: “proto: syntax error (line 2:16): invalid value п” | в одном из полей запроса невалидный формат |
|  400 | Bad Request | “error”: “proto: syntax error (line 2:16): unexpected token ,”} | пустое значение в одном из полей |
|  401 | Unauthorized | Unauthorized | невалидный API-ключ |
|  401 | Unauthorized | malformed token | API-ключ не задан |
|  404 | Not Found |  | некорректный URL-адрес запроса |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
