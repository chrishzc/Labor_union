module: weekly-operations-report
parent_subsystem: reporting
architecture: ../../../../../../../domains/global/subsystems/reporting/modules/weekly-operations-report.md
layout_status: custom_current
test_root: tests/test_weekly_operations_report_contract.py
higher_boundary:
  - ui_react/src/tests/reports_query_page.test.tsx
  - ui_react/src/tests/weekly_operations_report_client.test.ts

# Owned verification
- `tests/test_weekly_operations_report_contract.py` — strict API、selected-week owner facts、aggregate與三worksheet contract。
- `ui_react/src/tests/reports_query_page.test.tsx` — 週別選擇、三分頁與stale export presentation。
- `ui_react/src/tests/weekly_operations_report_client.test.ts` — canonical week conversion與typed transport contract。
