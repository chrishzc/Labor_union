module: weekly-operations-report
parent_subsystem: reporting
architecture: ../../../../../../../domains/global/subsystems/reporting/modules/weekly-operations-report.md
layout_status: custom_current
test_root: tests/test_weekly_operations_report_contract.py
higher_boundary:
  - ui_react/src/tests/reports_query_page.test.tsx
  - ui_react/src/tests/reports_weekly_service_display.test.tsx
  - ui_react/src/tests/weekly_operations_report_client.test.ts

# Owned verification
- `tests/test_weekly_operations_report_contract.py` — strict API、selected-period案件／服務 facts、`end_date` 年度補助 candidate、跨民國申請年度摘要 aggregate與三worksheet contract。
- `ui_react/src/tests/reports_query_page.test.tsx` — 週別選擇、三分頁與stale export presentation。
- `ui_react/src/tests/reports_weekly_service_display.test.tsx` — 服務工時資料、空狀態與查詢失敗呈現。
- `ui_react/src/tests/weekly_operations_report_client.test.ts` — canonical week conversion與typed transport contract。
