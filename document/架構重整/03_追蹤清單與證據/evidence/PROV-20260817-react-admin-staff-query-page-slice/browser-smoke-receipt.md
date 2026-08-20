# Staff query page-slice browser smoke receipt

Status: `PASS_QUERY_SUCCESS_PATH`（2026-08-17）

使用者在既有Chrome完成password→TOTP；Integration Owner沿用同一volatile Session，以既有DB做GET-only
觀察，未讀取或記錄帳密、TOTP、token或cookie：

1. Network confirms one initial `GET /api/v1/staff/summaries?page_size=200`.
2. At least one redacted response `id/name/phone` matches the DOM card.
3. Drawer/tab interactions issue no extra GET/non-GET.
4. If `next_cursor` exists, one manual click issues exactly one forward cursor GET.
5. Logout/session expiry is not rendered as empty data.

實測：Uvicorn記錄單一`GET /api/v1/staff/summaries?page_size=200`為200；DOM顯示server id/name/phone、
null phone顯示後端未提供、主檔／證照／銀行／偏好／lifecycle槽位unavailable，新增與離職等控制native
disabled。Focused tests另覆蓋Drawer/tab 0 request、empty/error、cursor與stale。驗收視窗0 non-GET。

結論：G6 success path PASS；package達`query-real-data-validated`。Shell system-status 401／離線badge屬既有
Shell owner finding，不影響Staff GET。
