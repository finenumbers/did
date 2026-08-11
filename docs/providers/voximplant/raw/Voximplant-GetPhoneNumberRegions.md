> For a complete documentation index, fetch https://docs.voximplant.ai/llms.txt

# GetPhoneNumberRegions

POST https://api.voximplant.com/platform_api/GetPhoneNumberRegions

Get the country regions of the phone numbers. The response also contains the info about multiple numbers subscription for the child accounts.

Allowed roles: `Owner`, `Admin`, `Accountant`, `Payer`.

**Example request:** Get the Russian regions of the phone numbers.

Reference: https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers/get-phone-number-regions

## Authentication

- `Authorization` header (bearer token, required) — Voximplant Management API uses signed JWT tokens generated from your service-account private key. Pass the token in the `Authorization` header as a Bearer value: ``` Authorization: Bearer $VOXIMPLANT_TOKEN ``` See [Authorization](/api-reference/management-api/authorization) for ready-to-copy snippets in bash, Python, Node.js and Go that turn your `credentials.json` into a token.

## Request

### Query parameters

- `country_code` (string, required) — The country code
- `phone_category_name` (string, required) — The phone category name. See the [GetPhoneNumberCategories] method
- `country_state` (string, optional) — The country state code (example: AL, CA, ... )
- `omit_empty` (boolean, optional, default: true) — Whether not to show all the regions (with and without phone numbers in stock)
- `phone_region_id` (integer, optional) — The phone region ID to filter
- `phone_region_name` (string, optional) — The phone region name to filter
- `phone_region_code` (string, optional) — The region phone prefix to filter
- `locale` (string, optional) — The 2-letter locale code. Supported values are EN, RU

## Response

### 200

Successful response

- `result` (list of object, optional)
  - `phone_region_id` (integer, optional) — The region ID
  - `phone_region_name` (string, optional) — The full region name
  - `phone_region_code` (string, optional) — The region phone prefix
  - `phone_count` (integer, optional) — The phone number count in stock for the region
  - `verification_status` (string, optional) — The account verification status. Available only for RU accounts. The following values are possible: REQUIRED, IN_PROGRESS
  - `required_verification` (string, optional) — Country code, where the verification is required for the account. Currently, the only possible value for this field is `RU` (Russia)
  - `phone_period` (string, optional) — The charge period in 24-h format: Y-M-D H:m:s. Example: 0-1-0 0:0:0 is 1 month
  - `is_need_regulation_address` (boolean, optional) — Whether to need proof of address
  - `regulation_address_type` (string, optional) — The type of regulation address. The possible values are LOCAL, NATIONAL, WORLDWIDE
  - `is_sms_supported` (boolean, optional) — Whether SMS is supported for phone numbers in this region. SMS needs to be explicitly enabled for a phone number via the \[ControlSms] Management API before sending or receiving SMS. If SMS is supported and enabled, SMS can be sent from a phone number via the \[SendSmsMessage] Management API and received via the \[InboundSmsCallback] property of the HTTP callback. See this article for HTTP callback details
  - `multiple_numbers_price` (list of object, optional) — [Array](MultipleNumbersPrice) with info about multiple numbers subscription for the child accounts
    - `count` (integer, optional) — The number of subscriptions which must be purchased simultaneously to enable a multiple numbers subscription
    - `installation_tax_reserve` (integer, optional) — The phone number installation tax reserve
    - `tax_reserve` (integer, optional) — The phone number tax reserve
    - `local_price` (integer, optional) — Phone number price from the price list
    - `local_installation_price` (integer, optional) — Phone number installation price from the price list
    - `local_currency` (string, optional) — Price list currency
    - `account_price` (integer, optional) — Phone number price in the account currency
    - `account_installation_price` (integer, optional) — Phone number installation price in the account currency
    - `account_currency` (string, optional) — Account currency
    - `price` (double, optional)
    - `installation_price` (integer, optional)
  - `localized_country_name` (string, optional) — The localized country name
  - `localized_phone_category_name` (string, optional) — The localized phone category name
  - `localized_phone_region_name` (string, optional) — The localized phone region name
  - `phone_installation_tax_reserve` (integer, optional) — The phone number installation tax reserve
  - `phone_tax_reserve` (integer, optional) — The phone number tax reserve
  - `local_price` (integer, optional) — Phone number price from the price list
  - `local_installation_price` (integer, optional) — Phone number installation price from the price list
  - `local_currency` (string, optional) — Price list currency
  - `account_price` (integer, optional) — Phone number price in the account currency
  - `account_installation_price` (integer, optional) — Phone number installation price in the account currency
  - `account_currency` (string, optional) — Account currency
  - `phone_price` (double, optional)
  - `phone_installation_price` (double, optional)

## Examples

**Response**

```json
{
  "result": [
    {
      "phone_region_id": 1,
      "phone_region_name": "Moscow",
      "phone_region_code": "499",
      "phone_count": 1123,
      "verification_status": "REQUIRED",
      "required_verification": "RU",
      "phone_period": "0-1-0 0:0:0",
      "multiple_numbers_price": [
        {
          "count": 10,
          "price": 0.4,
          "installation_price": 10
        }
      ],
      "phone_price": 0.45,
      "phone_installation_price": 10.2
    },
    {
      "phone_region_id": 3,
      "phone_region_name": "Novosibirsk",
      "phone_region_code": "383",
      "phone_count": 95,
      "phone_period": "0-1-0 0:0:0",
      "multiple_numbers_price": [],
      "phone_price": 0.5,
      "phone_installation_price": 2
    }
  ]
}
```

**SDK Code**

```python Example 1
import requests

url = "https://api.voximplant.com/platform_api/GetPhoneNumberRegions"

querystring = {"country_code":"country_code","phone_category_name":"phone_category_name"}

headers = {"Authorization": "Bearer <token>"}

response = requests.post(url, headers=headers, params=querystring)

print(response.json())
```

```javascript Example 1
const url = 'https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name';
const options = {method: 'POST', headers: {Authorization: 'Bearer <token>'}};

try {
  const response = await fetch(url, options);
  const data = await response.json();
  console.log(data);
} catch (error) {
  console.error(error);
}
```

```go Example 1
package main

import (
	"fmt"
	"net/http"
	"io"
)

func main() {

	url := "https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name"

	req, _ := http.NewRequest("POST", url, nil)

	req.Header.Add("Authorization", "Bearer <token>")

	res, _ := http.DefaultClient.Do(req)

	defer res.Body.Close()
	body, _ := io.ReadAll(res.Body)

	fmt.Println(res)
	fmt.Println(string(body))

}
```

```ruby Example 1
require 'uri'
require 'net/http'

url = URI("https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name")

http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true

request = Net::HTTP::Post.new(url)
request["Authorization"] = 'Bearer <token>'

response = http.request(request)
puts response.read_body
```

```java Example 1
import com.mashape.unirest.http.HttpResponse;
import com.mashape.unirest.http.Unirest;

HttpResponse<String> response = Unirest.post("https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name")
  .header("Authorization", "Bearer <token>")
  .asString();
```

```php Example 1
<?php
require_once('vendor/autoload.php');

$client = new \GuzzleHttp\Client();

$response = $client->request('POST', 'https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name', [
  'headers' => [
    'Authorization' => 'Bearer <token>',
  ],
]);

echo $response->getBody();
```

```csharp Example 1
using RestSharp;

var client = new RestClient("https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name");
var request = new RestRequest(Method.POST);
request.AddHeader("Authorization", "Bearer <token>");
IRestResponse response = client.Execute(request);
```

```swift Example 1
import Foundation

let headers = ["Authorization": "Bearer <token>"]

let request = NSMutableURLRequest(url: NSURL(string: "https://api.voximplant.com/platform_api/GetPhoneNumberRegions?country_code=country_code&phone_category_name=phone_category_name")! as URL,
                                        cachePolicy: .useProtocolCachePolicy,
                                    timeoutInterval: 10.0)
request.httpMethod = "POST"
request.allHTTPHeaderFields = headers

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