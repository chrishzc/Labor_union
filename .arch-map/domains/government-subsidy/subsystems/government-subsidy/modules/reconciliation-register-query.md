# Module: reconciliation-register-query

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
依已因訂金核銷成立、服務中或已完成的 Orders facts 與有效服務結束日產生獨立季度／年度報表；另為營運報表依 `end_date` 年度產生維持專用欄位格式的正常／歷史訂單補助統計 rows。正式 claim batch `submitted_at` 的 bounded 送件期間 query 保留為 Government Subsidy owner 能力，但不再供營運報表使用。

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
- outbound: 季／年度與營運年度統計均使用 Orders lifecycle、Client 補助身分與訂單服務 facts；營運年度統計另納入同等已付訂金語意的歷史 Orders 狀態，不依賴 claim batch 或 Scheduling generation。

## Contracts
- Government Subsidy reconciliation formula — `document/架構重整/01_規格基線/14_Government_Subsidy_Domain.md`
- 營運報表專用年度補助統計契約 — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/`
- higher-boundary consumer verification is owned by the Global Reporting weekly-operations-report Module.

## Provenance
- 季／年度成立訂單納入、有效服務結束日歸屬與訂單補助公式由Government Subsidy query owner組成 — `architecture_declared` — `14_Government_Subsidy_Domain.md`與current source。
- 營運報表補助分頁使用 `end_date` 年度、有效服務結束日衍生的核銷年度／季度、既有專用欄位格式及正常／歷史已付訂金訂單候選 — `architecture_declared` — `14_Government_Subsidy_Domain.md`、正式規格§15.1與current source。

## Change triggers
Reconcile when claim submission-period inclusion、成立訂單年季報表、補助公式、source roots 或 reporting contract 改變。
