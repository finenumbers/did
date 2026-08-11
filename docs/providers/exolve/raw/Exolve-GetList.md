Source: https://docs.exolve.ru/docs/ru/api-reference/numbering-api/reference/
Title: Метод GetList (справочник) | Numbering API | документация Exolve

- Документация
- Docs
- Документация
- API Reference
- Numbering API
- GetList (справочник)

# GetList (справочник)

## 
 Метод GetList

Примените метод GetList для получения справочника по характеристикам номеров (тип, категория, регион, и проект).
Точка подключения:
Выполните POST-запрос с входными параметрами к точке подключения:

```
`POST: https://api.exolve.ru/number/reference/v1/GetList
`
```

### 
 Авторизация

Передайте следующие Заголовки HTTP для успешной авторизации.
|  Имя | Тип | Описание |
|  Authorization | string | API-ключ приложения с `Bearer` перед ним. Пример: `Bearer e***s0`, где `e***s0` замените на API-ключ вашего приложения |

### 
 Входные параметры

Передайте пустой JSON в теле запроса.
|  Параметр | Описание |
|  {} | пустой JSON |

### 
 Выходные параметры

|  Параметр | Тип | Описание |
|  types | NumberTypes | сопоставляет наименование типа номера и его идентификатор |
|  categories | Categories | сопоставляет имя категории и ее идентификатор, а также принадлежащие к ней тип номера и его идентификатор |
|  regions | Regions | сопоставляет название региона с его идентификатором и кодом |

#### 
 NumberTypes

|  Параметр | Тип | Описание |
|  type_id | uint32 | идентификатор типа номера |
|  type_name | string | наименование типа номера |

#### 
 Categories

|  Параметр | Тип | Описание |
|  category_id | uint32 | идентификатор категории |
|  type_id | uint32 | идентификатор типа номера |
|  type_name | string | наименование типа номера |
|  category_name | string | имя категории |

#### 
 Regions

|  Параметр | Тип | Описание |
|  project_id | uint32 | идентификатор проекта |
|  region_id | uint32 | идентификатор региона |
|  parent_region_id | uint32 | идентификатор родительского региона |
|  region_code | string | код региона |
|  region_name | string | имя региона (латиница) |
|  description | string | имя региона (кириллица) |

### 
 Возможные ошибки

|  Код | Статус | Пример сообщения | Описание |
|  400 | Bad Request | proto: syntax error (line 1:2): unexpected token | некорректный формат запроса |
|  400 | Bad Request | proto: syntax error (line 1:2): invalid value | невалидный запрос |

### 
 Примеры

Входные параметры:

```
`{}
`
```

Выходные параметры:

```
`{
"regions": [
 {
"project_id": 10008,
"region_id": 10257,
"parent_region_id": 10084,
"region_code": "SLH",
"region_name": "Salekhard",
"description": "Салехард" }
 ],
"types": [
 {
"type_id": 1104,
"type_name": "DEF" }
 ],
"categories": [
 {
"category_id": 10003,
"type_id": 1107,
"type_name": "CEN",
"category_name": "REGULAR" }
 ]
}
`
```


 Навигация по документации
 Открыть


 Содержание статьиРазвернутьСвернуть
