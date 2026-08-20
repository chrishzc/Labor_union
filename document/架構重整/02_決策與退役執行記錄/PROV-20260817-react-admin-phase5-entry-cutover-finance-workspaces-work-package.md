---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-finance-workspaces
date: 2026-08-17
owner: Finance / Entry Governance Integration Owner
domain: Client Finance / Staff Payables / Government Subsidy / Reporting
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-public-outcome-contract PASS; PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening PASS; PROV-20260817-react-admin-phase4a-fi-r-finance-import-react PASS; PROV-20260817-react-admin-phase4b-ap-public-contract-hardening PASS; PROV-20260817-react-admin-phase4b-ap-r-react PASS; PROV-20260817-react-admin-phase4b-client-finance-public-contract-hardening PASS; PROV-20260817-react-admin-phase4b-cf-r-client-finance-react PASS; PROV-20260817-react-admin-phase4b-staff-payout-public-contract-hardening PASS; PROV-20260817-react-admin-phase4b-sp-r-staff-payout-react PASS; PROV-20260817-government-subsidy-reporting-authority-decision PASS; PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening PASS; PROV-20260817-react-admin-phase4b-s-r-react PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Finance Workspaces Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Finance workspaces entry readiness工作包

## Identity與範圍

Streamlit `ui:04_finance.py`／rollback `finance`，對應React `ui-react:#finance`與
`ui-react:#reports`的一對多workspace group。Subsidy presentation的canonical owner必須先人工裁決；AP或Subsidy
單一slice完成不等於整個Finance entry replacement。本包不修改production pages/clients。

## Exact write set

- `ui_react/src/tests/finance_entry_cutover.test.tsx`（new）
- `ui_react/src/tests/reports_entry_cross_owner_cutover.test.tsx`（new）
- `tests/test_react_finance_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-finance-workspaces/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`readiness-candidate`，不得標cutover／replacement／active。

## 必要門

1. receipts、staff payables、refunds、subsidy、bank import、AP/report逐workspace凍結owner/SSOT/query/export/mutation matrix。
2. Finance Import、AP、Client Finance、Staff Payout及Subsidy各自H/R與Durable Job prerequisite完成；其他未有
   typed successor的workspace必須原位unavailable，不能被隱藏或假接線。
3. server masking與binary download metadata通過；完整銀行帳號、身分證、raw ledger不進DOM/log/receipt。
4. 所有財務mutation維持native disabled，0 local settled/paid/refund/subsidy成功與0 `alert/confirm`。
5. 真browser驗AP period/export、Subsidy period/query、download failure、same-scope Streamlit oracle及rollback。
6. 最高狀態為`partial-workspace-candidate`；只有所有workspace閉合才能替代`ui:04_finance.py`。

`PROV-20260817-react-admin-phase4b-weekly-workbook-authority-gap`未經人工裁決時，generic weekly workbook與
三sheet報表必須unavailable；不得因AP/Subsidy named report完成就把Reports標full replacement。

Current Finance/Reports任何embedded ledger/business row、local settled/paid/refund/subsidy mutation、假XLSX
或`alert/confirm`固定`BLOCKED_MOCK_REMAINDER`。Binary export需驗metadata、content digest與typed failure，不能用
按鈕點擊或下載檔存在代替。Queue/manifest/readiness只由Integration Owner更新。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（candidate包0 DB change），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
