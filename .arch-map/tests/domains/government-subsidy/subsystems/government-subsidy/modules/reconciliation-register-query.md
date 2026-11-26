module: reconciliation-register-query
parent_subsystem: government-subsidy
architecture: ../../../../../../../domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query.md
layout_status: canonical
test_root: tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/
# Owned verification
- formal claim submission period uses `subsidy_claim_batches.submitted_at`, includes both boundaries, uses frozen claim-item values, and does not substitute service completion year。
- quarterly/annual query contracts include normal and equivalent paid-deposit historical established orders, use effective service end, prefer the case's frozen Payroll rate snapshot for subsidy unit price, and preserve XLSX-aligned fields without requiring a claim batch。
- operations-report annual candidate includes normal／historical deposit-established statuses, keeps its own application-year plus prior-year carry-in selection, derives reconciliation year／quarter from effective service end, and remains independent of claim batch state。
- `WEEKLY-SUB-01～03`：`test_subsidy_reconciliation_register.py::test_operations_report_counts_established_unserved_once_with_zero_subsidy_without_claim` 驗一案一列、跨年、無排班／費率、非市民、取消及正常有服務列。正式核銷排除須以同一筆資料做對照。業務規則用既有替身來源及 `Weekly report API contracts`，不另跑 DB 全套；測試定位不等於已執行。
