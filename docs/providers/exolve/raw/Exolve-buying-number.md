# Как купить номер (API excerpt)

Source: https://docs.exolve.ru/docs/ru/instructions/buying-number/

## Покупка номера через API

1. Получение списка свободных номеров для покупки — GetFree  
2. Бронирование номера — Lock  
3. Покупка номера — Buy  

Product integration is **read-only**: only step 1 (GetFree) is used.

### Пример получения свободных номеров из Postman

```
POST https://api.exolve.ru/number/v1/GetFree
```

Auth: Bearer Token = API-ключ приложения.

```json
{
    "type_id": 1105,
    "region_id": 10230,
    "category_id": 10001,
    "random": true,
    "mask": "7499%",
    "limit": 10,
    "offset": 0
}
```

Numbering API GetFree examples likewise always include `category_id` (e.g. Moscow DEF `10000`, KDU Silver `10022`).
