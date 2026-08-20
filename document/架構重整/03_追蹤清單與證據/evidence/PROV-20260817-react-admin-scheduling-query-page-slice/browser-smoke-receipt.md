# Browser Smoke Receipt

- Status: `PASS_QUERY_SUCCESS_PATH`
- Date: 2026-08-17
- Evidence: 使用者完成真password→TOTP後，Uvicorn記錄`GET /api/v1/staff/summaries?page_size=20`與
  `GET /api/v1/scheduling/staff/531/current-calendar?range_start=2026-08-01&range_end=2026-08-31`均200。
  DOM顯示郭萱、staff #531、projection token、8月1–31日server availability；leave／holiday／inbox／
  matching／precision全部unavailable/native disabled。Focused tests覆蓋月份/selector request budget、empty/error。
- Data boundary: 既有 DB 只允許 GET UI observation；不得 mutation、seed、repair 或 migration。
- Result: `query-real-data-validated`；驗收視窗0 non-GET。
