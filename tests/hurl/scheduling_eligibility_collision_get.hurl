# File: scheduling_eligibility_collision_get.hurl
# Description: 以唯讀 GET 驗證 case＋staff＋as-of bounded eligibility/collision projection。

GET {{base_url}}/api/v1/orders/summaries?page_size=1
HTTP 200
[Captures]
case_no: jsonpath "$.data.items[0].case_no"

GET {{base_url}}/api/v1/staff/summaries?page_size=1
HTTP 200
[Captures]
staff_id: jsonpath "$.data.items[0].id"

GET {{base_url}}/api/v1/scheduling/eligibility-collisions?case_no={{case_no}}&staff_id={{staff_id}}&as_of=2026-08-21
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data.case_no" == "{{case_no}}"
jsonpath "$.data.as_of" == "2026-08-21"
jsonpath "$.data.staff" count == 1
