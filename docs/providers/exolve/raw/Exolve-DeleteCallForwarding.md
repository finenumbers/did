Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/deleting-call-forwarding/
Title: Метод DeleteCallForwarding | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- DeleteCallForwarding

# DeleteCallForwarding

## 
 Метод DeleteCallForwarding

Примените метод DeleteCallForwarding для удаления настроек переадресации входящих вызовов на номере.

Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/v1/DeleteCallForwarding
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
|  number_code | uint64 | код номера |

### 
 Выходные параметры

Пустой JSON с 200 OK статусом.

### 
 Примеры

Входные параметры:

```
`{
"number_code": 74951341115}
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
|  400 | Bad Request | proto: syntax error (line 2:20): invalid value п | значение в поле `number_code` невалидно |
|  400 | Bad Request | proto: (line 3:1): invalid value for uint64 type: } | не задано значение в поле `number_code` |


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
