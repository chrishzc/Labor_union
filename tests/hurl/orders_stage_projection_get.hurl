# File: orders_stage_projection_get.hurl
# Description: 以唯讀 GET 驗證 Orders 七階段、十一作業步驟與唯一 membership 契約。

GET {{base_url}}/api/orders/operational-timelines?page_size=1
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data.items" count == 1
jsonpath "$.data.items[0].stages" count == 7
jsonpath "$.data.items[0].sop_steps" count == 11
jsonpath "$.data.items[0].stages[6].settlement" count == 3
jsonpath "$.data.items[0].projection_digest" matches /^[0-9a-f]{64}$/
