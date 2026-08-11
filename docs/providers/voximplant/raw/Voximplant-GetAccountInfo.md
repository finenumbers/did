> For a complete documentation index, fetch https://docs.voximplant.ai/llms.txt

# GetAccountInfo

POST https://api.voximplant.com/platform_api/GetAccountInfo

Gets the account's info such as account_id, account_name, account_email etc.

**Example request:** Get the account's info.

Reference: https://docs.voximplant.ai/api-reference/management-api/reference/accounts/get-account-info

## Authentication

- `Authorization` header (bearer token, required) — Voximplant Management API uses signed JWT tokens generated from your service-account private key. Pass the token in the `Authorization` header as a Bearer value: ``` Authorization: Bearer $VOXIMPLANT_TOKEN ``` See [Authorization](/api-reference/management-api/authorization) for ready-to-copy snippets in bash, Python, Node.js and Go that turn your `credentials.json` into a token.

## Request

### Query parameters

- `return_live_balance` (boolean, optional, default: true) — Whether to get the account's live balance

## Response

### 200

Successful response

- `result` (object, optional) — Account's info as the [AccountInfoType] object instance
  - `account_id` (integer, optional) — The account's ID
  - `account_name` (string, optional) — The account's name
  - `account_email` (string, optional) — The account's email
  - `api_key` (string, optional) — The account API key. Use password or api_key authentication to show the api_key
  - `account_first_name` (string, optional) — The first name
  - `account_last_name` (string, optional) — The last name
  - `created` (string, optional) — Timestamp in YYYY-MM-DD HH:mm:ss format. The UTC account created time in 24-h format: YYYY-MM-DD HH:mm:ss
  - `language_code` (string, optional) — The notification language code (2 symbols, ISO639-1). Examples: en, ru
  - `location` (string, optional) — The account location (timezone). Examples: America/Los_Angeles, Etc/GMT-8, Etc/GMT+10
  - `min_balance_to_notify` (double, optional) — The min balance value to notify by email or SMS
  - `account_notifications` (boolean, optional) — Whether Voximplant notifications are required
  - `tariff_changing_notifications` (boolean, optional) — Whether Voximplant plan changing notifications are required
  - `news_notifications` (boolean, optional) — Whether Voximplant news notifications are required
  - `billing_address_name` (string, optional) — The company or businessman name
  - `billing_address_country_code` (string, optional) — The billing address country code (2 symbols, ISO 3166-1 alpha-2). Examples: US, RU, GB
  - `billing_address_address` (string, optional) — The office address
  - `billing_address_zip` (string, optional) — The office ZIP
  - `billing_address_phone` (string, optional) — The office phone number
  - `billing_address_state` (string, optional) — The office state (US) or province (Canada), up to 100 characters. Examples: California, Illinois, British Columbia
  - `active` (boolean, optional) — Whether the account is active
  - `frozen` (boolean, optional) — Whether account is blocked by Voximplant admins
  - `balance` (double, optional) — The account's money
  - `credit_limit` (double, optional) — The account's credit limit
  - `currency` (string, optional) — The currency code (USD, RUR, EUR, ...)
  - `support_robokassa` (boolean, optional) — Whether Robokassa payments are allowed
  - `support_bank_card` (boolean, optional) — Whether Bank card payments are allowed
  - `support_invoice` (boolean, optional) — Whether Bank invoices are allowed
  - `account_custom_data` (string, optional) — The custom data
  - `access_entries` (list of string, optional) — The allowed access entries (the API function names)
  - `with_access_entries` (boolean, optional, default: false) — Whether the admin user permissions are granted
  - `callback_url` (string, optional) — If URL is specified, Voximplant cloud makes HTTP POST requests to it when something happens. For a full list of reasons see the **type** field of the [AccountCallback] structure. The HTTP request has a JSON-encoded body that conforms to the [AccountCallbacks] structure
  - `callback_salt` (string, optional) — If salt string is specified, each HTTP request made by the Voximplant cloud toward the **callback_url** has a **salt** field set to MD5 hash of account information and salt. That hash can be used be a developer to ensure that HTTP request is made by the Voximplant cloud
  - `send_js_error` (boolean, optional) — Whether to send an email when a JS error occurs
  - `billing_limits` (object, optional) — The payments limits applicable to each payment method
    - `robokassa` (object, optional) — The Robokassa limits
      - `min_amount` (double, optional) — The minimum amount
      - `currency` (string, optional) — The currency
    - `bank_card` (object, optional) — The bank card limits
      - `min_amount` (double, optional) — The minimum amount
      - `currency` (string, optional) — The currency
      - `max_day_payment` (double, optional)
    - `invoice` (object, optional) — The invoice limits
      - `min_amount` (double, optional) — The minimum amount
      - `currency` (string, optional) — The currency
  - `a2p_sms_enabled` (boolean, optional) — Whether to activate one-way SMS
  - `max_sip_registrations` (integer, optional)
  - `fixed_balance` (double, optional)
  - `money_on_hold` (double, optional)
  - `bank_card_provider` (string, optional)
  - `enabled_3ds` (boolean, optional)
  - `record_storage_id` (integer, optional)
  - `mobile_phone` (string, optional)
  - `allow_invoice` (boolean, optional)
  - `is_bank_card_auto_charge_prohibited` (boolean, optional)
  - `taxpayer_type` (string, optional)
  - `custom_pricing` (boolean, optional)
  - `grace_credit` (integer, optional)
  - `record_storage_name` (string, optional)
  - `credit_limit_aware_balance_notifications` (boolean, optional)
  - `live_balance` (double, optional)
- `api_address` (string, optional) — The preferred address for the Management API requests
- `debugger_address` (string, optional)

## Examples

**Request**

```json
{}
```

**Response**

```json
{
  "result": {
    "account_id": 3456750,
    "account_name": "ivan123",
    "account_email": "ivan123@mail.ru",
    "created": "2020-08-07 12:00:53",
    "language_code": "en",
    "location": "Europe/Moscow",
    "min_balance_to_notify": 300,
    "account_notifications": true,
    "tariff_changing_notifications": true,
    "news_notifications": true,
    "active": true,
    "frozen": false,
    "balance": 19772.35,
    "credit_limit": 0,
    "currency": "RUR",
    "support_robokassa": false,
    "support_bank_card": true,
    "support_invoice": true,
    "send_js_error": false,
    "billing_limits": {
      "bank_card": {
        "min_amount": 500,
        "currency": "RUR",
        "max_day_payment": 7642.17
      },
      "invoice": {
        "min_amount": 1000,
        "currency": "RUR"
      }
    },
    "a2p_sms_enabled": false,
    "max_sip_registrations": 0,
    "fixed_balance": 20169.93,
    "money_on_hold": 397.58,
    "bank_card_provider": "ALFABANK",
    "enabled_3ds": true,
    "record_storage_id": 125,
    "mobile_phone": "+7-495-123-4567",
    "allow_invoice": true,
    "is_bank_card_auto_charge_prohibited": true,
    "taxpayer_type": "default",
    "custom_pricing": false,
    "grace_credit": 0,
    "record_storage_name": "my-storage",
    "credit_limit_aware_balance_notifications": false,
    "live_balance": 19772.35
  },
  "api_address": "api-node1.voximplant.com",
  "debugger_address": "api-node1.voximplant.com"
}
```

**SDK Code**

```python Account's info
import requests

url = "https://api.voximplant.com/platform_api/GetAccountInfo"

payload = {}
headers = {
    "Authorization": "Bearer <token>",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)

print(response.json())
```

```javascript Account's info
const url = 'https://api.voximplant.com/platform_api/GetAccountInfo';
const options = {
  method: 'POST',
  headers: {Authorization: 'Bearer <token>', 'Content-Type': 'application/json'},
  body: '{}'
};

try {
  const response = await fetch(url, options);
  const data = await response.json();
  console.log(data);
} catch (error) {
  console.error(error);
}
```

```go Account's info
package main

import (
	"fmt"
	"strings"
	"net/http"
	"io"
)

func main() {

	url := "https://api.voximplant.com/platform_api/GetAccountInfo"

	payload := strings.NewReader("{}")

	req, _ := http.NewRequest("POST", url, payload)

	req.Header.Add("Authorization", "Bearer <token>")
	req.Header.Add("Content-Type", "application/json")

	res, _ := http.DefaultClient.Do(req)

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)

	fmt.Println(res)
	fmt.Println(string(body))

}
```

```ruby Account's info
require 'uri'
require 'net/http'

url = URI("https://api.voximplant.com/platform_api/GetAccountInfo")

http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true

request = Net::HTTP::Post.new(url)
request["Authorization"] = 'Bearer <token>'
request["Content-Type"] = 'application/json'
request.body = "{}"

response = http.request(request)
puts response.read_body
```

```java Account's info
import com.mashape.unirest.http.HttpResponse;
import com.mashape.unirest.http.Unirest;

HttpResponse<String> response = Unirest.post("https://api.voximplant.com/platform_api/GetAccountInfo")
  .header("Authorization", "Bearer <token>")
  .header("Content-Type", "application/json")
  .body("{}")
  .asString();
```

```php Account's info
<?php
require_once('vendor/autoload.php');

$client = new \GuzzleHttp\Client();

$response = $client->request('POST', 'https://api.voximplant.com/platform_api/GetAccountInfo', [
  'body' => '{}',
  'headers' => [
    'Authorization' => 'Bearer <token>',
    'Content-Type' => 'application/json',
  ],
]);

echo $response->getBody();
```

```csharp Account's info
using RestSharp;

var client = new RestClient("https://api.voximplant.com/platform_api/GetAccountInfo");
var request = new RestRequest(Method.POST);
request.AddHeader("Authorization", "Bearer <token>");
request.AddHeader("Content-Type", "application/json");
request.AddParameter("application/json", "{}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

```swift Account's info
import Foundation

let headers = [
  "Authorization": "Bearer <token>",
  "Content-Type": "application/json"
]
let parameters = [] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

let request = NSMutableURLRequest(url: NSURL(string: "https://api.voximplant.com/platform_api/GetAccountInfo")! as URL,
                                        cachePolicy: .useProtocolCachePolicy,
                                    timeoutInterval: 10.0)
request.httpMethod = "POST"
request.allHTTPHeaderFields = headers
request.httpBody = postData as Data

let session = URLSession.shared
let dataTask = session.dataTask(with: request as URLRequest, completionHandler: { (data, response, error) -> Void in
  if (error != nil) {
    print(error as Any)
  } else {
    let httpResponse = response as? HTTPURLResponse
    print(httpResponse)
  }
})

dataTask.resume()
```