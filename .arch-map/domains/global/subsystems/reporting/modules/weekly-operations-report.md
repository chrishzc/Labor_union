# Module: weekly-operations-report

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
以canonical Monday `week_start`協調selected week內案件、補助完成列與Scheduling正式工作日，提供strict JSON及同candidate XLSX；不得把year-to-date資料混入週報。

## Implementation
- primary:
  - `subsystems/reporting/weekly_operations_report_query.py`
  - `subsystems/reporting/weekly_operations_report_export.py`
  - `infrastructure/mysql/weekly_operations_report_query_adapter.py`
  - `ui_react/src/pages/ReportsPage.tsx`
- entrypoints:
  - `api/routes/operations_reports.py`
  - `ui_react/src/api/reports/weekly_operations_report_query_client.ts`
  - `ui_react/src/api/reports/weekly_operations_report_export_client.ts`

## Dependencies
- outbound: `government-subsidy/reconciliation-register-query` — 以owner formula取得服務完成日落在selected week的補助rows。
- outbound: `orders | client | scheduling` — selected-week案件與正式服務facts。
- inbound: authenticated React Reports page。

## Contracts
- `weekly-operations-report.v1`與canonical `week_start` — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_weekly_operations_report_contract.py`
- integration_root: `ui_react/src/tests/reports_query_page.test.tsx`
- integration_root: `ui_react/src/tests/weekly_operations_report_client.test.ts`

## Provenance
- Global Reporting擁有跨Domain週報composition，business formula仍由各owner提供 — `architecture_declared` — 正式規格§15.1與current source。
- flat Python contract path由entrypoint review generator直接消費且本身證明cross-domain API／XLSX boundary — `source_observed` — `scripts/generate_entrypoint_review_queue.py`。

## Change triggers
Reconcile when週界、補助期間、三分頁schema、owner fact dependency、public GET/export或Reports presentation test path改變。
