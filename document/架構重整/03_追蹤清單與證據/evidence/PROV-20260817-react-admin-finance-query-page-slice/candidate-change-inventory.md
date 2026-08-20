# Candidate Change Inventory

## Backend

- Client Receipt GET、Staff Payables GET與四個Finance Import GET改用`require_admin`；同檔mutations未改。
- AP preview加入`require_admin`及server masking；schema只改JSON preview欄位。
- `finance_reports.py` export/archive/subsidy routes與XLSX workflow未改。

## React

- 新增四組bounded schemas/errors/clients與四個adapters。
- `FinancePage.tsx/.css`改為active-tab lazy GET；移除mock/local settled/paid/alert/XLSX/fake mutations。
- 新增去敏fixtures與client/adapter/page/no-fake tests。

Boundary：0 DB/schema migration/seed/backfill、0 provider/job/outbox、0 ReportsPage/Orders/Staff/shared/package變更。

