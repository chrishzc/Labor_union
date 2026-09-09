# Module: reconciliation-register-query

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
依已因訂金核銷成立、服務中或已完成的 Orders facts 與有效服務結束日產生獨立季度／年度報表，並以正式 claim batch `submitted_at` 產生營運週報的 bounded 送件期間唯讀核銷 rows。

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
- outbound: 季／年度使用 Orders lifecycle、Client 補助身分與訂單服務 facts；營運週報使用 Government Subsidy current-revision claim batches/items。

## Contracts
- Government Subsidy reconciliation formula — `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- 營運週報selected-week補助契約 — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/`
- higher-boundary consumer verification is owned by the Global Reporting weekly-operations-report Module.

## Provenance
- 季／年度成立訂單納入、有效服務結束日歸屬與訂單補助公式由Government Subsidy query owner組成 — `architecture_declared` — `14_Government_Subsidy_Domain.md`與current source。

## Change triggers
Reconcile when claim submission-period inclusion、成立訂單年季報表、補助公式、source roots 或 reporting contract 改變。
