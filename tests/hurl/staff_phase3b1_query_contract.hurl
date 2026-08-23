# File: staff_phase3b1_query_contract.hurl
# Description: 以唯讀 GET 驗證 Staff selector、preferences、availability 與 lifecycle public query。

GET {{base_url}}/api/v1/staff/summaries?page_size=1
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data.items" count == 1
[Captures]
staff_id: jsonpath "$.data.items[0].id"

GET {{base_url}}/api/v1/staff/summaries?after_id=1&staff_id=2
HTTP 422
[Asserts]
jsonpath "$.detail.error.category" == "validation"
jsonpath "$.detail.error.code" == "staff_summary_query_params_conflict"

GET {{base_url}}/api/v1/scheduling/staff-matching-preferences/definitions
HTTP 200
[Asserts]
jsonpath "$.success" == true
jsonpath "$.data" isList

GET {{base_url}}/api/v1/scheduling/staff-matching-preferences/staff/{{staff_id}}
HTTP 200
[Asserts]
jsonpath "$.success" == true
jsonpath "$.data.staff_id" == {{staff_id}}

GET {{base_url}}/api/v1/scheduling/staff/{{staff_id}}/availability-blocks?range_start=2026-01-01&range_end=2026-12-31
HTTP 200
[Asserts]
jsonpath "$.success" == true
jsonpath "$.data" isList

GET {{base_url}}/api/v1/staff/{{staff_id}}/lifecycle
HTTP 200
[Asserts]
jsonpath "$.success" == true
jsonpath "$.data.staff_id" == {{staff_id}}
