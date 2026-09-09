# Module: reconciliation-register-query

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
依正式 claim batch `application_year + quarter` 及 frozen item values 產生獨立季度／年度報表，並以正式 claim batch `submitted_at` 產生營運週報的 bounded 送件期間唯讀核銷 rows；不接受 Reporting 重算補助單價、上限或 root facts。

## Implementation
- primary:
  - `subsystems/government_subsidy/reconciliation_register_query.py`
  - `api/routes/finance_reports.py`
  - `api/routes/finance_reports.py::_subsidy_report_row`
  - `api/routes/finance_reports.py::_subsidy_report_view`
  - `api/routes/finance_reports.py::preview_quarterly_reconciliation`
  - `api/routes/finance_reports.py::preview_annual_reconciliation`

## Dependencies
- inbound: `global/reporting/weekly-operations-report` — selected-period formal claim submission readback。
- outbound: Government Subsidy current-revision claim batches/items，以及 Orders／Client／item-owned Staff 顯示 facts。

## Contracts
- Government Subsidy reconciliation formula — `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- 營運週報selected-week補助契約 — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/`
- higher-boundary consumer verification is owned by the Global Reporting weekly-operations-report Module.

## Provenance
- 季／年度歸屬、frozen補助值及item-owned staff由Government Subsidy owner擁有 — `architecture_declared` — `14_Government_Subsidy_Domain.md`與current source。

## Change triggers
Reconcile when claim submission-period inclusion、claim batch年季報表、frozen item projection、source roots 或 reporting contract 改變。
