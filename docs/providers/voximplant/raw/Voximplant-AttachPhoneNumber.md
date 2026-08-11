> For a complete documentation index, fetch https://docs.voximplant.ai/llms.txt

# AttachPhoneNumber

POST https://api.voximplant.com/platform_api/AttachPhoneNumber

Attach the phone number to the account. Note that phone numbers of some countries may require additional verification steps.

Please note that when you purchase a phone number, we reserve the subscription fee and taxes for the upcoming month. Read more in the Billing page.

Allowed roles: `Owner`, `Admin`, `Accountant`.

**Example request:** Attach a US phone number to the account 1.

Reference: https://docs.voximplant.ai/api-reference/management-api/reference/phone-numbers/attach-phone-number

## Authentication

- `Authorization` header (bearer token, required) — Voximplant Management API uses signed JWT tokens generated from your service-account private key. Pass the token in the `Authorization` header as a Bearer value: ``` Authorization: Bearer $VOXIMPLANT_TOKEN ``` See [Authorization](/api-reference/management-api/authorization) for ready-to-copy snippets in bash, Python, Node.js and Go that turn your `credentials.json` into a token.

## Request

### Query parameters

- `phone_count` (integer, optional) — Quantity of phone numbers you want to attach. **Required** unless **phone_number** is provided.
- `phone_number` (list of string, optional) — The phone number. See the [GetNewPhoneNumbers] method. **Required** unless **phone_count** is provided.
- `country_code` (string, required) — The country code
- `phone_category_name` (string, required) — The phone category name. See the [GetPhoneNumberCategories] method
- `country_state` (string, optional) — The country state. See the [GetPhoneNumberCategories] and [GetPhoneNumberCountryStates] methods
- `phone_region_id` (integer, required) — The phone region ID. See the [GetPhoneNumberRegions] method
- `regulation_address_id` (integer, optional) — The phone regulation address ID

## Response

### 200

Successful response

- `result` (integer, optional) — Returns 1 if the request has been completed successfully
- `phone_numbers` (list of object, optional) — The attached phone numbers
  - `phone_id` (integer, optional) — The phone ID
  - `phone_number` (string, optional) — The phone number
  - `required_verification` (string, optional) — Country code, where the verification is required for the account. Currently, the only possible value for this field is `RU` (Russia)
  - `verification_status` (string, optional) — The account verification status. Available only for RU accounts. The following values are possible: REQUIRED, IN_PROGRESS
  - `unverified_hold_until` (string, optional) — Date string as returned by the Management API. Unverified phone hold until the date in the following format: YYYY-MM-DD (if the account verification is required). The number is detached on that day automatically!
- `error` (object, optional)
  - `code` (integer, optional)
  - `msg` (string, optional)
  - `details` (object, optional)
    - `verification_name` (string, optional)

## Examples

### Success

**Request**

```json
{}
```

**Response**

```json
{
  "result": 1,
  "phone_numbers": [
    {
      "phone_id": 12,
      "phone_number": "15552850126"
    }
  ]
}
```

**SDK Code**

```python Success
import requests

url = "https://api.voximplant.com/platform_api/AttachPhoneNumber"

querystring = {"country_code":"US","phone_category_name":"local","phone_region_id":"101","phone_number":"[\"+15552850126\"]"}

payload = {}
headers = {
    "Authorization": "Bearer <token>",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers, params=querystring)

print(response.json())
```

```javascript Success
const url = 'https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D';
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

```go Success
package main

import (
	"fmt"
	"strings"
	"net/http"
	"io"
)

func main() {

	url := "https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D"

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

```ruby Success
require 'uri'
require 'net/http'

url = URI("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")

http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true

request = Net::HTTP::Post.new(url)
request["Authorization"] = 'Bearer <token>'
request["Content-Type"] = 'application/json'
request.body = "{}"

response = http.request(request)
puts response.read_body
```

```java Success
import com.mashape.unirest.http.HttpResponse;
import com.mashape.unirest.http.Unirest;

HttpResponse<String> response = Unirest.post("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")
  .header("Authorization", "Bearer <token>")
  .header("Content-Type", "application/json")
  .body("{}")
  .asString();
```

```php Success
<?php
require_once('vendor/autoload.php');

$client = new \GuzzleHttp\Client();

$response = $client->request('POST', 'https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D', [
  'body' => '{}',
  'headers' => [
    'Authorization' => 'Bearer <token>',
    'Content-Type' => 'application/json',
  ],
]);

echo $response->getBody();
```

```csharp Success
using RestSharp;

var client = new RestClient("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D");
var request = new RestRequest(Method.POST);
request.AddHeader("Authorization", "Bearer <token>");
request.AddHeader("Content-Type", "application/json");
request.AddParameter("application/json", "{}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

```swift Success
import Foundation

let headers = [
  "Authorization": "Bearer <token>",
  "Content-Type": "application/json"
]
let parameters = [] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

let request = NSMutableURLRequest(url: NSURL(string: "https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")! as URL,
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

### The account verification required: RU

**Request**

```json
{}
```

**Response**

```json
{
  "result": 1,
  "phone_numbers": [
    {
      "phone_id": 12,
      "phone_number": "15552850126"
    }
  ]
}
```

**SDK Code**

```python The account verification required: RU
import requests

url = "https://api.voximplant.com/platform_api/AttachPhoneNumber"

querystring = {"country_code":"US","phone_category_name":"local","phone_region_id":"101","phone_number":"[\"+15552850126\"]"}

payload = {}
headers = {
    "Authorization": "Bearer <token>",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers, params=querystring)

print(response.json())
```

```javascript The account verification required: RU
const url = 'https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D';
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

```go The account verification required: RU
package main

import (
	"fmt"
	"strings"
	"net/http"
	"io"
)

func main() {

	url := "https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D"

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

```ruby The account verification required: RU
require 'uri'
require 'net/http'

url = URI("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")

http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true

request = Net::HTTP::Post.new(url)
request["Authorization"] = 'Bearer <token>'
request["Content-Type"] = 'application/json'
request.body = "{}"

response = http.request(request)
puts response.read_body
```

```java The account verification required: RU
import com.mashape.unirest.http.HttpResponse;
import com.mashape.unirest.http.Unirest;

HttpResponse<String> response = Unirest.post("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")
  .header("Authorization", "Bearer <token>")
  .header("Content-Type", "application/json")
  .body("{}")
  .asString();
```

```php The account verification required: RU
<?php
require_once('vendor/autoload.php');

$client = new \GuzzleHttp\Client();

$response = $client->request('POST', 'https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D', [
  'body' => '{}',
  'headers' => [
    'Authorization' => 'Bearer <token>',
    'Content-Type' => 'application/json',
  ],
]);

echo $response->getBody();
```

```csharp The account verification required: RU
using RestSharp;

var client = new RestClient("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D");
var request = new RestRequest(Method.POST);
request.AddHeader("Authorization", "Bearer <token>");
request.AddHeader("Content-Type", "application/json");
request.AddParameter("application/json", "{}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

```swift The account verification required: RU
import Foundation

let headers = [
  "Authorization": "Bearer <token>",
  "Content-Type": "application/json"
]
let parameters = [] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

let request = NSMutableURLRequest(url: NSURL(string: "https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")! as URL,
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

### The overdue account verification in progress

**Request**

```json
{}
```

**Response**

```json
{
  "result": 1,
  "phone_numbers": [
    {
      "phone_id": 12,
      "phone_number": "15552850126"
    }
  ]
}
```

**SDK Code**

```python The overdue account verification in progress
import requests

url = "https://api.voximplant.com/platform_api/AttachPhoneNumber"

querystring = {"country_code":"US","phone_category_name":"local","phone_region_id":"101","phone_number":"[\"+15552850126\"]"}

payload = {}
headers = {
    "Authorization": "Bearer <token>",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers, params=querystring)

print(response.json())
```

```javascript The overdue account verification in progress
const url = 'https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D';
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

```go The overdue account verification in progress
package main

import (
	"fmt"
	"strings"
	"net/http"
	"io"
)

func main() {

	url := "https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D"

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

```ruby The overdue account verification in progress
require 'uri'
require 'net/http'

url = URI("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")

http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true

request = Net::HTTP::Post.new(url)
request["Authorization"] = 'Bearer <token>'
request["Content-Type"] = 'application/json'
request.body = "{}"

response = http.request(request)
puts response.read_body
```

```java The overdue account verification in progress
import com.mashape.unirest.http.HttpResponse;
import com.mashape.unirest.http.Unirest;

HttpResponse<String> response = Unirest.post("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")
  .header("Authorization", "Bearer <token>")
  .header("Content-Type", "application/json")
  .body("{}")
  .asString();
```

```php The overdue account verification in progress
<?php
require_once('vendor/autoload.php');

$client = new \GuzzleHttp\Client();

$response = $client->request('POST', 'https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D', [
  'body' => '{}',
  'headers' => [
    'Authorization' => 'Bearer <token>',
    'Content-Type' => 'application/json',
  ],
]);

echo $response->getBody();
```

```csharp The overdue account verification in progress
using RestSharp;

var client = new RestClient("https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D");
var request = new RestRequest(Method.POST);
request.AddHeader("Authorization", "Bearer <token>");
request.AddHeader("Content-Type", "application/json");
request.AddParameter("application/json", "{}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

```swift The overdue account verification in progress
import Foundation

let headers = [
  "Authorization": "Bearer <token>",
  "Content-Type": "application/json"
]
let parameters = [] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

let request = NSMutableURLRequest(url: NSURL(string: "https://api.voximplant.com/platform_api/AttachPhoneNumber?country_code=US&phone_category_name=local&phone_region_id=101&phone_number=%5B%22%2B15552850126%22%5D")! as URL,
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