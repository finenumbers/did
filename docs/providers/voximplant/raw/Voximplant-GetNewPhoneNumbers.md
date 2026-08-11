> For a complete documentation index, fetch https://docs.voximplant.ai/llms.txt

# GetNewPhoneNumbers

POST https://api.voximplant.com/platform_api/GetNewPhoneNumbers

Gets the new phone numbers.

Allowed roles: `Owner`, `Admin`, `Accountant`.

**Example request:** Get the two new fixed Russian phone numbers at max.

Reference: https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers/get-new-phone-numbers

## Authentication

- `Authorization` header (bearer token, required) — Voximplant Management API uses signed JWT tokens generated from your service-account private key. Pass the token in the `Authorization` header as a Bearer value: ``` Authorization: Bearer $VOXIMPLANT_TOKEN ``` See [Authorization](/api-reference/management-api/authorization) for ready-to-copy snippets in bash, Python, Node.js and Go that turn your `credentials.json` into a token.

## Request

### Query parameters

- `country_code` (string, required) — The country code
- `phone_category_name` (string, required) — The phone category name. See the [GetPhoneNumberCategories] function
- `country_state` (string, optional) — The country state. See the GetPhoneNumberCategories and GetPhoneNumberCountryStates functions
- `phone_region_id` (integer, required) — The phone region ID. See the [GetPhoneNumberRegions] method
- `count` (integer, optional, default: 20) — The max returning record count
- `offset` (integer, optional, default: 0) — The first **N** records are skipped in the output
- `phone_number_mask` (string, optional) — The phone number searching mask. Asterisk represents zero or more occurrences of any character

## Response

### 200

Successful response

- `result` (list of object, optional)
  - `phone_id` (integer, optional) — The phone ID
  - `phone_number` (string, optional) — The phone number
  - `phone_price` (double, optional) — The phone monthly fee. It consists of `phone_price` and `phone_tax_reserve`
  - `phone_installation_price` (double, optional) — The phone installation price (without the first monthly fee). It consists of `phone_installation_price` and `phone_installation_tax_reserve`
  - `phone_country_code` (string, optional) — The phone country code (2 symbols)
  - `phone_period` (string, optional) — The charge period in 24-h format: Y-M-D H:m:s. Example: 0-1-0 0:0:0 is 1 month
  - `phone_category_name` (string, optional) — The phone category name (MOBILE, GEOGRAPHIC, TOLLFREE, MOSCOW495)
  - `phone_region_name` (string, optional) — The phone region name
  - `phone_installation_tax_reserve` (integer, optional) — The phone number installation tax reserve. The phone installation price consists of `phone_installation_price` and `phone_installation_tax_reserve`
  - `phone_tax_reserve` (integer, optional) — The phone number tax reserve. The phone monthly fee consists of `phone_price` and `phone_tax_reserve`
- `total_count` (integer, optional) — The total found phone count
- `count` (integer, optional) — The returned phone count

## Examples

**Response**

```json
{
  "result": [
    {
      "phone_id": 10,
      "phone_number": "74957893798",
      "phone_price": 0.45,
      "phone_installation_price": 10.2,
      "phone_country_code": "RU",
      "phone_period": "0-1-0 0:0:0",
      "phone_category_name": "GEOGRAPHIC"
    },
    {
      "phone_id": 12,
      "phone_number": "78332606030",
      "phone_price": 0.5,
      "phone_installation_price": 11.3,
      "phone_country_code": "RU",
      "phone_period": "0-1-0 0:0:0",
      "phone_category_name": "GEOGRAPHIC"
    }
  ],
  "total_count": 400,
  "count": 2
}
```

**SDK Code**

```python Example 1
import requests

url = "https://api.voximplant.com/platform_api/GetNewPhoneNumbers"

querystring = {"country_code":"country_code","phone_category_name":"phone_category_name","phone_region_id":"1"}

headers = {"Authorization": "Bearer <token>"}

response = requests.post(url, headers=headers, params=querystring)

print(response.json())
```

```javascript Example 1
const url = 'https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1';
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

	url := "https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1"

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

url = URI("https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1")

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

HttpResponse<String> response = Unirest.post("https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1")
  .header("Authorization", "Bearer <token>")
  .asString();
```

```php Example 1
<?php
require_once('vendor/autoload.php');

$client = new \GuzzleHttp\Client();

$response = $client->request('POST', 'https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1', [
  'headers' => [
    'Authorization' => 'Bearer <token>',
  ],
]);

echo $response->getBody();
```

```csharp Example 1
using RestSharp;

var client = new RestClient("https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1");
var request = new RestRequest(Method.POST);
request.AddHeader("Authorization", "Bearer <token>");
IRestResponse response = client.Execute(request);
```

```swift Example 1
import Foundation

let headers = ["Authorization": "Bearer <token>"]

let request = NSMutableURLRequest(url: NSURL(string: "https://api.voximplant.com/platform_api/GetNewPhoneNumbers?country_code=country_code&phone_category_name=phone_category_name&phone_region_id=1")! as URL,
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