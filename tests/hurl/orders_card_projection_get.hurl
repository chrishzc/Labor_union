# File: orders_card_projection_get.hurl
# Description: 以唯讀 GET 驗證 selected order card composite 與欄位 owner metadata。

GET {{base_url}}/api/v1/orders/summaries?page_size=1
HTTP 200
[Asserts]
jsonpath "$.success" == true
jsonpath "$.data.items" count == 1
[Captures]
case_no: jsonpath "$.data.items[0].case_no"

GET {{base_url}}/api/v1/orders/{{case_no}}/card-projection
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data.case_no" == "{{case_no}}"
jsonpath "$.data.contact_phone.owner" exists
jsonpath "$.data.contact_address.owner" exists
jsonpath "$.data.assignment_segments.owner" exists
