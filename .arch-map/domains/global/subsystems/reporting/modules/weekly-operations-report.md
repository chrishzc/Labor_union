# Module: weekly-operations-report

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
以 canonical `start_date`／`end_date` 協調自選期間內案件與 Scheduling 正式工作日，按實際星期一至星期日分週；「補助案件統計表」則固定取得 `end_date` 所屬完整年度的 Government Subsidy owner rows，並依民國申請年度與身分類別組成頂端筆數／金額摘要，以既有專用欄位格式提供 strict JSON 及同 candidate XLSX，不得改套獨立「年度補助」報表格式。
案件年度累計自 1 月 1 日起算；正常與歷史訂單依相同業務狀態合併計數，JSON／XLSX 共用 Reporting classification。待辦看板另使用同一 owner 的獨立唯讀案件統計 GET，按匯入曆年／季度／月份計數，維持全年度累計，不查服務、補助或 weekly metrics；計數 adapter 不讀取姓名、地址或原始拒絕原因。

## Implementation
- primary:
  - `subsystems/reporting/weekly_operations_report_query.py`
  - `subsystems/reporting/weekly_operations_report_export.py`
  - `subsystems/reporting/weekly_report_metrics_service.py`
  - `infrastructure/mysql/weekly_operations_report_query_adapter.py`
  - `api/dependencies/operations_reports.py`
  - `api/schemas/operations_reports.py`
  - `db/schema_parts/218_weekly_report_metrics.sql`
  - `db/schema_parts/1035_weekly_report_metrics.sql`
  - `scripts/generate_entrypoint_review_queue.py`
  - `ui_react/src/pages/ReportsPage.tsx`
- entrypoints:
  - `api/routes/operations_reports.py`
  - `ui_react/src/api/reports/weekly_operations_report_query_client.ts`
  - `ui_react/src/api/reports/weekly_operations_report_schemas.ts`
  - `ui_react/src/api/reports/weekly_operations_report_export_client.ts`
  - `ui_react/src/api/reports/weekly_report_metrics_client.ts`

## Dependencies
- outbound: `government-subsidy/reconciliation-register-query` — 以 owner formula 取得 `end_date` 所屬年度的正常／歷史已付訂金訂單補助統計 rows，不要求 claim batch。
- outbound: `orders | client | scheduling` — selected-week案件與正式服務facts。
- inbound: authenticated React Reports page、Orders 待辦看板統計列。
- storage: current `weekly_report_metrics` uses Monday `week_start_date` as its key and nullable promotion／inquiry counts; fresh `218` and preserve `1035` provide the table. Released `1031` batch objects are historical compatibility only and have no current runtime reader／writer.

## Contracts
- React 週報日期欄位完成輸入並 blur／Enter 後才套用查詢，編輯中的局部年份不發出跨千年查詢；沿用既有欄位與重新載入入口，套用新期間立即清除舊報表／匯出可用狀態。
- `operations-report.v3`、canonical `start_date`／`end_date`與Monday-keyed weekly metrics — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。
- `GET /api/v1/operations-reports/case-statistics`、曆年計數與歷史狀態合併 — 同一正式規格 §15.2。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_weekly_operations_report_contract.py`
- integration_root: `ui_react/src/tests/reports_query_page.test.tsx`
- integration_root: `ui_react/src/tests/reports_weekly_service_display.test.tsx`
- integration_root: `ui_react/src/tests/weekly_operations_report_client.test.ts`
- integration_root: `ui_react/src/tests/reports_entry_cross_owner_cutover.test.tsx`
- integration_root: `ui_react/src/tests/fixtures/reports/weekly_operations_report_contract_fixtures.ts`

## Provenance
- Global Reporting擁有跨Domain營運報表composition，business formula仍由各owner提供 — `architecture_declared` — 正式規格§15.1；現行source差異見上節。
- flat Python contract path由entrypoint review generator直接消費且本身證明cross-domain API／XLSX boundary — `source_observed` — `scripts/generate_entrypoint_review_queue.py`。

## Change triggers
Reconcile when報表期間／annual_ytd、補助期間、三分頁schema、owner fact dependency、public GET/export、批次POST／PATCH、writer／commit boundary、正式契約或Reports presentation test path改變。
