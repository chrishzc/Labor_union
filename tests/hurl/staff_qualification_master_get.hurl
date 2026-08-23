# File: staff_qualification_master_get.hurl
# Description: 以唯讀 GET 驗證 selected staff 六區 qualification master 與 PII 邊界。

GET {{base_url}}/api/v1/staff/summaries?page_size=1
HTTP 200
[Captures]
staff_id: jsonpath "$.data.items[0].id"

GET {{base_url}}/api/v1/staff/{{staff_id}}/qualification-master?as_of=2026-08-21
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data.staff_id" == {{staff_id}}
jsonpath "$.data.sections" count == 6
jsonpath "$.data.phone" not exists
jsonpath "$.data.address" not exists
jsonpath "$.data.email" not exists
