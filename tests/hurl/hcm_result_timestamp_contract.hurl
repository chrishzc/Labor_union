# File: hcm_result_timestamp_contract.hurl
# Description: 驗證 HCM Result Review 完成時間符合帶 Asia/Taipei offset 的 RFC3339 契約。

GET {{base_url}}/api/v1/case-import/hcm/workbooks/results?limit=1
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data.items" count == 1
jsonpath "$.data.items[0].completed_at" matches /\+08:00$/
