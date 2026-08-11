Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/unlocking-number/
Title: Метод Unlock | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- Unlock

# Unlock

## 
 Метод Unlock

Примените метод Unlock для отмены бронирования номера.

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/Unlock
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
|  number_code | uint64 | номер |
|  uid | uint32 | идентификатор бронирования |

### 
 Выходные параметры

Пустой JSON с 200 OK статусом.

### 
 Примеры

Входные параметры:

```
`{
"number_code": 73412209107,
"uid": 1000988}
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
|  400 | Bad Request | proto: (line 4:1): invalid value for uint32 type: } | не задано значение в поле `uid` |
|  400 | Bad Request | proto: syntax error (line 3:20): invalid value к | значение в поле `uid` невалидно |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
