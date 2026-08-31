# Subsystem: reporting

## Parent
- domain: `global`

## Responsibility
協調各owner的唯讀facts形成跨Domain營運報表；不得重算或改寫Orders、Scheduling、Government Subsidy等business roots。

## Modules
- `weekly-operations-report` — 週一至週日的案件、補助與正式服務工時報表；path: `modules/weekly-operations-report.md`

## Dependencies
- outbound: `orders | client` — selected-week案件受理facts。
- outbound: `government-subsidy/reconciliation-register-query` — owner-calculated selected-week補助rows。
- outbound: `scheduling` — selected-week effective正式工作日。

## Contracts
- `GET /api/v1/operations-reports/weekly`與`/export` — `api/routes/operations_reports.py`
- 營運週報三分頁正式契約 — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1

## Verification routing
- default_boundary: Global
- module-owned verification: `modules/weekly-operations-report.md`
