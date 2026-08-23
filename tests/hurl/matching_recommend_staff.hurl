# File: matching_recommend_staff.hurl
# Description: 固化不存在案件的月嫂推薦查詢，避免資料欄位漂移重新造成 HTTP 500。

GET {{base_url}}/api/v1/matches/recommend-staff?case_no=NONEXISTENT-CASE
HTTP 200
[Asserts]
header "Content-Type" startsWith "application/json"
jsonpath "$.success" == true
jsonpath "$.data" isList

GET {{base_url}}/api/v1/matches/recommend-staff?case_no=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
HTTP 422
