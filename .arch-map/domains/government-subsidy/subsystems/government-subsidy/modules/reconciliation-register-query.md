# Module: reconciliation-register-query

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
依已因訂金核銷成立、服務中或已完成，或具有同等已付訂金語意的歷史 Orders facts、案件 Payroll 凍結費率與有效服務結束日產生獨立季度／年度報表；另為營運報表依 `end_date` 年度，選取同民國案件年度的正常／歷史訂單，以及上一民國案件年度但同西元核銷年度的 carry-in rows，並維持專用欄位格式。正式 claim batch `submitted_at` 的 bounded 送件期間 query 保留為 Government Subsidy owner 能力，但不再供營運報表使用。

## Implementation
- primary:
  - `subsystems/government_subsidy/reconciliation_register_query.py`
  - `api/routes/finance_reports.py`
  - `api/routes/finance_reports.py::_subsidy_report_row`
  - `api/routes/finance_reports.py::_subsidy_report_view`
  - `api/routes/finance_reports.py::preview_quarterly_reconciliation`
  - `api/routes/finance_reports.py::preview_annual_reconciliation`

## Dependencies
- inbound: `global/reporting/weekly-operations-report` — `end_date` 所屬年度的營運專用補助統計 readback。
- outbound: 季／年度與營運年度統計均使用 Orders lifecycle、Client 補助身分、訂單服務 facts 與案件 Payroll 凍結費率，並納入同等已付訂金語意的歷史 Orders 狀態；未形成 claim item 時只以 Payroll 快照為單價，缺少快照即 fail closed，不得退回身分別單價；不依賴 claim batch 或 Scheduling generation。

## Contracts
- Government Subsidy reconciliation formula — `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- 營運報表專用年度補助統計契約 — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/`
- higher-boundary consumer verification is owned by the Global Reporting weekly-operations-report Module.

## Provenance
- 季／年度正常及同等已付訂金歷史訂單納入、有效服務結束日歸屬、案件 Payroll 凍結費率優先與訂單補助公式由Government Subsidy query owner組成 — `architecture_declared` — `14_Government_Subsidy_Domain.md`與current source。
- 營運報表補助分頁使用 `end_date` 年度；同民國案件年度均為候選，上一民國案件年度僅在有效服務結束日衍生的核銷年度等於報表西元年度時帶入，並保留既有專用欄位格式及正常／歷史已付訂金狀態 — `architecture_declared` — `14_Government_Subsidy_Domain.md`、正式規格§15.1與current source。

## Change triggers
Reconcile when claim submission-period inclusion、正常／歷史成立訂單年季報表、補助公式、source roots 或 reporting contract 改變。
