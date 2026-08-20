---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-data-import-workspaces
date: 2026-08-17
owner: Case Import / Finance Import / Entry Governance Integration Owner
domain: Case Import / Finance Import / Staff / Orders
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-case-import-workbook-policy-decision PASS; PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract PASS; PROV-20260817-react-admin-phase4a-r-hcm-apply-react PASS; PROV-20260817-react-admin-phase4a-case-workbooks-public-contract-hardening PASS; PROV-20260817-react-admin-phase4a-cw-r-case-workbooks-react PASS; PROV-20260817-durable-job-core-persistence-worker-contract PASS; PROV-20260817-durable-job-public-outcome-contract PASS; PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening PASS; PROV-20260817-react-admin-phase4a-fi-r-finance-import-react PASS
conditional_prerequisites: PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening when Apply transitions warnings
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Data Import Workspaces Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-file-dialog-assisted
---

# Phase 5：Data Import workspaces entry readiness工作包

## Identity與範圍

Streamlit `ui:09_data_import.py`／rollback `data-import`／React主工作台`ui-react:#data-import`；
Finance Import可另映射`ui-react:#finance`，Anomalies只作warning downstream navigation。六個import families必須逐項
disposition；HCM Preview完成不能代表整entry完成。本包不修改production import page/client。

## Exact write set

- `ui_react/src/tests/data_import_entry_cutover.test.tsx`（new）
- `ui_react/src/tests/finance_import_entry_cutover.test.tsx`（new）
- `tests/test_react_data_import_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-data-import/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`readiness-candidate`，不得標cutover／replacement／active。

## 必要門

1. HCM current、Client BeClass、Staff historical、Historical Order、Finance Import逐類凍結
   owner/schema/warning/job/receipt/replay matrix；HCM historical whole-row overwrite固定410 retired，不是待接family。
2. HCM current須先完成4A-H/R與Source Archive Option A裁決；其他四個active families各用bounded client，
   不得建立generic import client或重新啟用HCM historical。
3. 未完成類別Preview/Apply在原位置native disabled；禁止random fingerprint、fixed sample、dirty-row假放行與local success。
4. 真browser controlled `.xlsx` upload覆蓋digest、preview、Apply（若核准）、warning、partial failure、
   outcome-unknown同key replay、receipt lookup與Anomalies navigation。
5. forward-written data在Streamlit rollback可query/repair/replay；`/?entry=data-import`精確可用。
6. 五個active families全部閉合且HCM historical明確呈現retired disposition，才能標整entry replacement；
   否則最高為`partial-workspace-candidate`。

每一family須有獨立scenario identity、client owner、rollback/replay與DB before/after row delta；HCM Preview不可
替其他family填PASS。Queue/manifest/readiness只由Integration Owner更新；任何Apply forward write未完成
receipt/outbox/job與Streamlit repair/replay證據時，本entry固定BLOCKED而非partial success。

DB：未核准Scope BLOCKED；Change inventory BLOCKED直到六family逐項分類forward writes；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
