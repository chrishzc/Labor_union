module: weekly-operations-report
parent_subsystem: reporting
architecture: ../../../../../../domains/global/subsystems/reporting/modules/weekly-operations-report.md
layout_status: custom_current
test_root: tests/test_weekly_operations_report_contract.py
higher_boundary:
  - ui_react/src/tests/reports_query_page.test.tsx
  - ui_react/src/tests/reports_weekly_totals.test.tsx
  - ui_react/src/tests/reports_weekly_api_versions.test.tsx
  - ui_react/src/tests/reports_weekly_service_display.test.tsx
  - ui_react/src/tests/weekly_operations_report_client.test.ts

# Owned verification
- `tests/domains/global/subsystems/reporting/modules/weekly-operations-report/test_weekly_operations_report_totals.py` — 以替身案件確認跨年週仍歸前一年 12 月小計，而同筆申請計入當年年度累計；同檔亦覆蓋選一週內部分日期時，明細受日期篩選，週指標不拆分。
- `tests/test_weekly_operations_report_contract.py` — strict API、selected-period案件／服務 facts、`end_date` 年度補助 candidate、跨民國申請年度摘要 aggregate與三worksheet contract。
- `ui_react/src/tests/reports_query_page.test.tsx` — 營運兩分頁、帳務唯一補助入口的14／15／10欄與原 XLSX、日期套用及 stale export presentation。
- `ui_react/src/tests/reports_weekly_totals.test.tsx` — 模板雙層表頭、既有明細指標、年度累計與月小計欄位對齊。
- `ui_react/src/tests/reports_weekly_api_versions.test.tsx` — v3／v4 可用性提示及缺值、版本錯誤呈現。
- `ui_react/src/tests/reports_weekly_service_display.test.tsx` — 以替身查詢回應核對服務工時、空狀態及查詢失敗；包括每日時數留空、週工時仍顯示的案例。不驗實際排班 SQL。
- `ui_react/src/tests/weekly_operations_report_client.test.ts` — canonical week conversion與typed transport contract。

# 逐日工時核對
- 業務情境見 [需求書 §2.2](../../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-service-daily-hours)。條款、SQL 與畫面接線見上方架構書。
- `tests/test_weekly_operations_report_mysql.py` 有 MySQL 報表與同期間 XLSX 的比對入口，不以此推定已覆蓋合併／分裂排班、跨週歸屬及兩端輸出。這組情境仍需單獨驗收。
