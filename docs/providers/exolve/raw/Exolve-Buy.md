Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/buying-number/
Title: Метод Buy | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- Buy

# Buy

## 
 Метод Buy

Примените метод Buy для покупки забронированного ранее номера.

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/Buy
`
```

### 
 Авторизация

Передайте следующие Заголовки HTTP для успешной авторизации.
|  Имя | Тип | Описание |
|  Authorization | string | API-ключ приложения с `Bearer` перед ним. Пример: `Bearer e***s0`, где `e***s0` замените на API-ключ вашего приложения |

### 
 Входные параметры

Передайте следующие параметры в теле запроса в JSON формате. Параметры, отмеченные жирным шрифтом, являются обязательными.
|  Параметр | Тип | Описание |
|  number_code | uint64 | номер |
|  reserve_uid | uint32 | идентификатор забронированного номера (возвращаемое поле `id` после выполнения запроса LockNumber) |
|  call_transcribation | boolean | текстовая расшифровка звонков. True — подключить, False — отключить |
|  speech_analytics | boolean | речевая аналитика звонков. True — подключить, False — отключить |

На всех новых номерах автоматически подключена запись разговора. Отключить её можно на 31-й день с момента покупки в Личном кабинете или с помощью API-метода GetAttributes. Изменение срока хранения записей доступно в настройках приложения в Личном кабинете.

Речевая аналитика уже включает в себя текстовую расшифровку звонка, поэтому подключить одновременно и аналитику, и транскрибацию нельзя — выберите одну из услуг

### 
 Выходные параметры

Пустой JSON с 200 OK статусом.

### 
 Примеры

Входные параметры:

```
`{
"number_code": 74996480010,
"reserve_uid": 1000993,
"call_transcribation": true}
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
|  400 | Bad Request | proto: syntax error (line 2:20): invalid value к | значение в поле `number_code` невалидно |
|  400 | Bad Request | proto: syntax error (line 2:20): unexpected token , | не задано значение в поле `number_code` |
|  400 | Bad Request | proto: (line 4:1): invalid value for uint32 type: } | не задано значение в поле `reserved_uid` |
|  400 | Bad Request | proto: syntax error (line 3:20): invalid value к | значение в поле `reserved_uid` невалидно |
|  400 | Bad Request | proto: “Error buying number: call transcribation and speech analytics cannot be enabled at the same time” | транскрибация и речевая аналитика не могут быть подключены одновременно |
|  400 | Bad Request | “call transcribation must be enabled in the application settings” | услуги транскрибации не может быть подключена, т.к. в настройках приложения уже подключена речевая аналитика |
|  400 | Bad Request | ““speech analytics must be enabled in the application setting” | услуги речевой аналитики не может быть подключена, т.к. в настройках приложения уже подключена транскрибация |
|  401 | Unauthorized | malformed token | не задан API-ключ |
|  401 | Unauthorized | unauthorized | невалидный API-ключ |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
