# Module: weekly-operations-report

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
以canonical `start_date`／`end_date` 協調自選期間內案件、補助完成列與Scheduling正式工作日，按實際星期一至星期日分週，提供strict JSON及同candidate XLSX；不得把year-to-date或批次封存資料混入營運報表。

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
  - `ui_react/src/api/reports/weekly_operations_report_export_client.ts`
  - `ui_react/src/api/reports/weekly_report_metrics_client.ts`

## Dependencies
- outbound: `government-subsidy/reconciliation-register-query` — 以owner formula取得服務完成日落在selected week的補助rows。
- outbound: `orders | client | scheduling` — selected-week案件與正式服務facts。
- inbound: authenticated React Reports page。
- storage: current `weekly_report_metrics` uses Monday `week_start_date` as its key and nullable promotion／inquiry counts; fresh `218` and preserve `1035` provide the table. Released `1031` batch objects are historical compatibility only and have no current runtime reader／writer.

## Contracts
- `operations-report.v3`、canonical `start_date`／`end_date`與Monday-keyed weekly metrics — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

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
