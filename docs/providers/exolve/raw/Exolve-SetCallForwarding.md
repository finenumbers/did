Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/call-forwarding/
Title: Метод SetCallForwarding | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- SetCallForwarding

# SetCallForwarding

## 
 Метод SetCallForwarding

Примените метод SetCallForwarding для настройки переадресации входящих вызовов на номере.

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/SetCallForwarding
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
|  number_code | uint64 | номер МТС Exolve, на который устанавливается переадресация |
|  call_forwarding_type | enum CallForwardingType | тип переадресации |
|  call_forwarding_data | oneof CallForwardingData | настройка переадресации |

#### 
 CallForwardingType

|  Параметр | Тип | Описание |
|  0 | enum | переадресация не определена |
|  1 | enum | переадресация на внешний SIP-аккаунт |
|  2 | enum | переадресация на номер или SIP ID платформы МТС Exolve |
|  3 | enum | динамическая переадресация по API (на URL) |
|  4 | enum | переадресация на SIP-транк (Static IP) |

#### 
 CallForwardingData

|  Параметр | Тип | Описание |
|  call_forwarding_sip | CallForwardingSip | данные для переадресации на внешний SIP-аккаунт |
|  call_forwarding_number | CallForwardingNumber | данные для переадресации на номер или SIP ID |
|  call_forwarding_ipcr | CallForwardingIpcr | данные для динамической переадресации по API (на URL) |
|  call_forwarding_static | CallForwardingStatic | данные для переадресации на SIP-транк (Static IP) |

#### 
 CallForwardingSip

|  Параметр | Тип | Описание |
|  sip_uri | string | URI-адрес SIP-аккаунта формата: {имя пользователя}@{домен или IP}:{порт} |

#### 
 CallForwardingNumber

|  Параметр | Тип | Описание |
|  redirect_type | enum RedirectType | тип переадресации |
|  call_control | CallControl | управление входящим вызовом |
|  event_url | string | URL для отправки уведомлений о ходе звонка |
|  event_extended | boolean | `True` для получения расширенных уведомлений. `False` для получения стандартного набора уведомлений |
|  client_id | string | сквозной идентификатор вызова от API клиента |
|  file_to_a | string | аудиосообщение звонящему абоненту |
|  file_to_b | string | аудиосообщение принимающему абоненту |
|  masking | boolean | `True` для скрытия номера звонящего абонента. `False` для показа оригинального номера звонящего абонента |
|  display_number | string | номер, который показывается абоненту C (номер переадресации). Зависит от параметра `masking`. Если `masking` — `False`, принимающему вызов показывается реальный номер звонящего. Если `masking` — `True`, можно передать любой номер Exolve, принадлежащий этому приложению |

#### 
 RedirectType

|  Параметр | Тип | Описание |
|  1 | enum | одиночная переадресация |
|  2 | enum | последовательная переадресация |
|  3 | enum | параллельная переадресация |

#### 
 CallControl

|  Параметр | Тип | Описание |
|  redirect_number | string | номер или юзернейм SIP ID для переадресации |
|  timeout | uint32 | время ожидания ответа в секундах |
|  active | boolean | `True` для переадресации вызова на `redirect_number`, `False` для сброса вызова |
|  name | string | произвольное имя номера для переадресации вызова |
|  period | string Period | расписание активности для переадресации вызова; значение передаётся в виде перечисления (разделитель – пробел) или диапазона (вида «от» и «до» включительно, разделитель – пробел) |
|  period_description | string | произвольное описание расписания активности для перенаправления вызова |

#### 
 Period

|  Параметр | Значение | Описание и допустимые значения |
|  year | yr | Год: 0-3000.  Пример: yr {2024-2026} |
|  month | mo | Месяц года: 1-12 или jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec или Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec. Пример: mo {Jan-Apr} или mo {jan feb nov dec} |
|  week | wk | Порядковая неделя в месяце: 1-6.  Пример: wk {1 3 5} или wk {1-2} |
|  yday | yd | Порядковый день года: 1-365.  Пример: yd {1-100} |
|  mday  | md  | День месяца: 1-31.  Пример: md {1-5} |
|  wday  | wd | День в неделе: 1-7 или mo, tu, we, th, fr, sa, su или Mo, Tu, We, Th, Fr, Sa, Su или mon, tue, wed, thu, fri, sat, sun или Mon, Tue, Wed, Thu, Fri, Sat, Sun.  Пример: wd {1 3 5 7} или wd {mo-fr} |
|  hour | hr | Час: 0-23 или 12am 1am-11am 12pm(12noon) 1pm-11pm.  Пример: hr {9am-4pm} |
|  minute | min | Минута: 0-59.  Пример: min {30-59} |
|  second | sec | Секунда: 0-59.  Пример: sec {1-5} |

#### 
 CallForwardingIpcr

|  Параметр | Тип | Описание |
|  url | string | URL-адрес для переадресации звонка |
|  reserve | string | резервный номер для переадресации, если URL будет недоступен |

#### 
 CallForwardingStatic

|  Параметр | Тип | Описание |
|  static_ip | string | IP адрес |
|  port | uint32 | порт |
|  timeout | uint32 | таймаут переадресации |
|  did | uint64 | DID номер |

### 
 Выходные параметры

Пустой JSON с 200 OK статусом.

### 
 Примеры

Входные параметры для переадресации на внешний SIP-аккаунт:

```
`{
"number_code": 74991112233,
"call_forwarding_type": 1,
"call_forwarding_sip": {
"sip_uri": "testsip06844538@testsip.test.ru" }
}
`
```

Входные параметры для переадресации на номер или SIP ID:

```
`{
"number_code": 74991112233,
"call_forwarding_type": 2,
"call_forwarding_number": {
"redirect_type": 1,
"call_control":[
 {
"timeout": "16",
"active": true,
"period": "wd {Mon-Fri} hr {6am-14pm}",
"period_description": "график будни",
"name": "звонит клиент",
"redirect_number": "74992223344"// или 883140XXXXXXXXX (SIP ID)
 }
 ],
"event_url": "https://example.com/",
"event_extended": true,
"client_id": "test",
"file_to_a": "12345",
"file_to_b": "54321",
"masking": true,
"display_number": "74995556677" }
}
`
```

Входные параметры для динамической переадресации по API (на URL):

```
`{
"number_code": 74991112233,
"call_forwarding_type": 3,
"call_forwarding_ipcr": {
"url": "https://example.com/",
"reserve": "74993334455" }
}
`
```

Входные параметры для переадресации на SIP-транк (Static IP):

```
`{
"number_code": 74991112233,
"call_forwarding_type": 4,
"call_forwarding_static": {
"static_ip": "127.0.0.1",
"port": 10,
"timeout": 30,
"did": 111 }
}
`
```

Выходные параметры:

```
`{}
`
```

### 
 Примечание к отправке уведомлений при входящем звонке

Вы можете настроить отправку уведомлений о ходе входящих звонков на URL-адрес вашего сервера двумя способами:
- 

Установить URL для определённого номера, передав значение в поле `event_url` при выполнения метода SetCallForwarding.
- 

Установить URL в настройках приложения в блоке «Уведомления о событиях» в Личном кабинете разработчика. Установленный URL применяется ко всем номерам приложения.

При отправке уведомлений о ходе входящего звонка платформа МТС Exolve сначала проверяет, указан ли URL индивидуально на номере вызова. Если URL не указан на номере, проверяет, указан ли в приложении. Подробнее:
- Если URL указан и на номере, и в приложении, уведомления будут отправлены на URL из индивидуальных настроек номера.
- Если URL указан на номере, но пуст в приложении, уведомления будут отправлены на URL из индивидуальных настроек номера.
- Если URL не указан на номере, но указан в приложении, уведомления будут отправлены на URL из приложения


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
