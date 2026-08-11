Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/getting-free-numbers/
Title: Метод GetFree | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- GetFree

# GetFree

## 
 Метод GetFree

Примените метод GetFree для получения списка номеров, доступных для покупки

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/GetFree
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
|  type_id | uint32 | тип номера |
|  region_id | uint32 | регион номера |
|  category_id | uint32 | категория номера |
|  random | boolean | `True` вернёт номера в случайном порядке |
|  mask | string | маска |
|  limit | uint32 | лимит выводимых строк |
|  offset | uint32 | номер строки, с которой начинать выборку (начинается с 0) |

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
 Маска

|  Символ | Назначение |
|  Точка ( . ) / Подчёркивание ( _ ) | пропускает один символ параметра `number_code` в поиске |
|  Звёздочка ( * ) / Знак процента ( % ) | пропускает несколько символов параметра `number_code` в поиске |

### 
 Выходные параметры

|  Параметр | Тип | Описание |
|  numbers | array NumberElement | список номеров с информацией по ним |

#### 
 NumberElement

|  Параметр | Тип | Описание |
|  type_name | string | наименование типа номера |
|  region_name | string | имя региона |
|  category_name | string | имя категории номера |
|  number_code | uint64 | код номера |
|  subscription_fee | float | ежемесячная абонентская плата |
|  install_fee | float | единоразовая плата за подключение |
|  number_options | array NumberOptions | возможности номера (звонки, SMS) |
 NumberOptions

|  Параметр | Тип | Описание |
|  incoming_calls | bool | входящие звонки, `True` — доступно, `False` — доступно |
|  outgoing_calls | bool | исходящие звонки, `True` — доступно, `False` — доступно |
|  incoming_sms | bool | входящие SMS, `True` — доступно, `False` — доступно |
|  outgoing_sms | bool | исходящие SMS, `True` — доступно, `False` — доступно |

### 
 Примеры

Пример получения свободных номеров для региона «Москва», категории «Обычный», тип «Мобильный»:

Входные параметры:

```
`{
"type_id": 1104,
"region_id": 10230,
"category_id": 10000,
"random": true,
"limit": 1}
`
```

Выходные параметры:

```
`{
"numbers": [
 {
"number_code": "79300655934",
"type_name": "DEF",
"region_name": "Moscow",
"category_name": "REGULAR",
"subscription_fee": 150,
"install_fee": 590,
"number_options": {
"incoming_calls": true,
"outgoing_calls": true,
"incoming_sms": true,
"outgoing_sms": true }
 }
 ]
}
`
```

Пример получения свободных номеров для региона «Санкт-Петербург», категории «Бронзовый», тип «Городской»:

Входные параметры:

```
`{
"type_id": 1105,
"region_id": 10182,
"category_id": 10011,
"random": true,
"mask": "781221*",
"limit": 1}
`
```

Выходные параметры:

```
`{
"numbers": [
 {
"number_code": "78122135222",
"type_name": "ABC",
"region_name": "St. Petersburg",
"category_name": "BRONZE",
"subscription_fee": 200,
"install_fee": 1000,
"number_options": {
"incoming_calls": true,
"outgoing_calls": true,
"incoming_sms": false,
"outgoing_sms": false }
 }
 ]
}
`
```

Пример получения свободных номеров для региона «Россия», категории «Серебряный», тип «Федеральный»:

Входные параметры:

```
`{
"type_id": 1106,
"region_id": 10084,
"category_id": 10022,
"random": true,
"limit": 1}
`
```

Входные параметры:

```
`{
"numbers": [
 {
"number_code": "78003333729",
"type_name": "KDU",
"region_name": "Russia",
"category_name": "SILVER",
"subscription_fee": 3500,
"install_fee": 50000,
"number_options": {
"incoming_calls": true,
"outgoing_calls": false,
"incoming_sms": false,
"outgoing_sms": false }
 }
 ]
}
`
```

### 
 Возможные ошибки

|  Код | Статус | Пример сообщения | Описание |
|  400 | Bad Request | proto: syntax error (line 1:2): unexpected token | пустое значение в поле `type_id` |
|  400 | Bad Request | proto: syntax error (line 1:2): invalid value | значение в поле `type_id` невалидно |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
