# Candidate Change Inventory

## Backend

- `api/schemas/government_subsidy_report.py`：strict redacted report views。
- `api/routes/finance_reports.py`：只新增季度／年度`require_admin`、typed materialization、masking與metadata。
- 既有AP require_admin/masked helpers/schema、AP export/archive及所有subsidy export routes保持原樣。

## React

- 新增Reports schemas/errors/client與adapter。
- ReportsPage改為季度／年度active GET；weekly兩slots unavailable；所有exports disabled。
- 移除mock arrays、local KPIs、alert與fake XLSX。
- 新增去敏fixture與client/adapter/page/no-fake tests。

Boundary：0 DB/schema migration/seed/backfill、0 provider/job/outbox、0 FinancePage/shared/package變更。

