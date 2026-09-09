# Module: weekly-operations-report

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
路由案件、補助完成列與Scheduling正式工作日的JSON Query／XLSX export、三分頁呈現，以及同一路由下現行週報批次結算與指標寫入。自選期間與唯讀要求屬正式契約；現行 `annual_ytd` 與批次writer的差異另列於下，不將source行為升格為已核准規格。

## Implementation
- primary:
  - `subsystems/reporting/weekly_operations_report_query.py`
  - `subsystems/reporting/weekly_operations_report_export.py`
  - `subsystems/reporting/weekly_report_batch_service.py` — 現行批次查詢、結算、案件綁定與指標更新；service直接commit。
  - `infrastructure/mysql/weekly_operations_report_query_adapter.py`
  - `scripts/generate_entrypoint_review_queue.py`
  - `ui_react/src/pages/ReportsPage.tsx`
- entrypoints:
  - `api/routes/operations_reports.py`
  - `ui_react/src/api/reports/weekly_operations_report_query_client.ts`
  - `ui_react/src/api/reports/weekly_operations_report_export_client.ts`

## Dependencies
- outbound: `government-subsidy/reconciliation-register-query` — 以owner formula取得服務完成日落在實際查詢期間的補助rows。
- outbound: `orders | clients | scheduling` — 實際查詢期間的案件與正式服務facts。
- inbound: authenticated React Reports page。
- storage: `weekly_report_batches` and `weekly_report_batch_cases` are provided by the separated fresh `217` or preserve `1031` schema release chain.

## Contracts
- `operations-report.v2`、自選 `start_date`／`end_date`、唯讀Query及不保存workbook的同candidate export — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Observed implementation / contract differences
核對source revision：`56c4c3765b572f4d934bd9926fd8ba25d7d35f0f`。以下均為 `source_observed`，不是新的契約或compliance結論。

- `GET /api/v1/operations-reports/weekly`與`GET /api/v1/operations-reports/weekly/export`均接受 `annual_ytd`（預設false）。`WeeklyOperationsReportQuery.query()` 在true時以 `date(end_date.year, 1, 1)` 取代傳入的 `start_date`，false時保留傳入起日；不可將現行實作描述為始終只使用自選起訖。
- `POST /api/v1/operations-reports/weekly/batches` 呼叫 `WeeklyReportBatchService.close_batch()`，寫入 `weekly_report_batches` 與 `weekly_report_batch_cases`；`PATCH /api/v1/operations-reports/weekly/batches/{batch_id}` 呼叫 `update_batch_metrics()`，更新批次指標及可選週碼／備註。兩個service方法均直接呼叫 `self._conn.commit()`；不是唯讀Query，也不能據此宣稱已遵守Global outer UoW契約。
- 這些entrypoints位於 `api/routes/operations_reports.py`，由 `api/main.py` 掛載 `operations_reports.router`。本leaf引用的§15.1仍定義自選期間的唯讀Query／export；上述YTD分支、批次寫入及service-owned commit須與該契約分開呈現，不能以程式已存在推定規格已修訂。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_weekly_operations_report_contract.py`
- integration_root: `ui_react/src/tests/reports_query_page.test.tsx`
- integration_root: `ui_react/src/tests/weekly_operations_report_client.test.ts`
- integration_root: `ui_react/src/tests/reports_entry_cross_owner_cutover.test.tsx`
- integration_root: `ui_react/src/tests/fixtures/reports/weekly_operations_report_contract_fixtures.ts`

## Provenance
- Global Reporting擁有跨Domain營運報表composition，business formula仍由各owner提供 — `architecture_declared` — 正式規格§15.1；現行source差異見上節。
- flat Python contract path由entrypoint review generator直接消費且本身證明cross-domain API／XLSX boundary — `source_observed` — `scripts/generate_entrypoint_review_queue.py`。

## Change triggers
Reconcile when報表期間／annual_ytd、補助期間、三分頁schema、owner fact dependency、public GET/export、批次POST／PATCH、writer／commit boundary、正式契約或Reports presentation test path改變。
