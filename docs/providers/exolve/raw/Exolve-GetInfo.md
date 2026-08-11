Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/purchased-number/
Title: Метод GetInfo (купленный номер) | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- GetInfo (купленный номер)

# GetInfo (купленный номер)

## 
 Метод GetInfo

Примените метод GetInfo для получения информации о купленном номере.

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/customer/v1/GetInfo
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
|  number_code | uint64 | купленный номер |

### 
 Выходные параметры

|  Параметр | Тип | Описание |
|  number_name | string | номер |
|  type_name | string | тип номера |
|  region_name | string | региона |
|  application_name | string | название приложения, в котором куплен номер |
|  subscription_fee | float | ежемесячная абонентская плата |
|  install_fee | float | единоразовая плата за подключение |
|  create_date | string | дата покупки номера в формате RFC-3339 / ISO-8601 |
|  application_uuid | string | идентификатор приложения |
|  category_name | string | наименование категории |
|  number_options | array NumberOptions | возможности номера (звонки, SMS) |
 NumberOptions

|  Параметр | Тип | Описание |
|  incoming_calls | bool | входящие звонки, `True` — доступно, `False` — доступно |
|  outgoing_calls | bool | исходящие звонки, `True` — доступно, `False` — доступно |
|  incoming_sms | bool | входящие SMS, `True` — доступно, `False` — доступно |
|  outgoing_sms | bool | исходящие SMS, `True` — доступно, `False` — доступно |

### 
 Примеры

Входные параметры:

```
`{ 
"number_code": 79011550006}
`
```

Выходные параметры:

```
`{
"number": {
"number_name": "79991234455",
"type_name": "DEF",
"region_name": "Moscow",
"application_name": "FLOWERSHOP24/7",
"subscription_fee": 150,
"install_fee": 590,
"create_date": "2025-06-11T07:50:31.807946Z",
"application_uuid": "c9c5031b-ad9b-4453-b6f8-bd5b14455790",
"category_name": "REGULAR",
"number_options": {
"incoming_calls": true,
"outgoing_calls": true,
"incoming_sms": true,
"outgoing_sms": true }
 }
}
`
```


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
