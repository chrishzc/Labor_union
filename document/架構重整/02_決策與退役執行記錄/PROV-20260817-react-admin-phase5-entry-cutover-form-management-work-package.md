---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-form-management
date: 2026-08-17
owner: Form Management / Entry Governance Integration Owner
domain: Orders / Staff / Reporting (identity undecided)
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS
blocking_gap: PROV-20260817-form-template-catalog-owner-public-contract-gap
prerequisite_resolution: form-template-catalog-owner-gap-must-be-resolved-by-human-decision
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Form Management Entry Readiness Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Form Management entry identity／readiness工作包

## Identity與阻塞

Streamlit `ui:05_form_management.py`／rollback `form-management`。目前11頁React baseline沒有
`#form-management`或對等page；`#orders`、`#staff`、`#reports`只涵蓋局部surface，不得拼成假replacement。
本包只建立identity/owner/readiness evidence，不執行cutover。

唯一current前置決策是 `PROV-20260817-form-template-catalog-owner-public-contract-gap`。該gap未由人工關閉前
不得預先命名production API、owner或React successor；Phase5A只登錄identity，不替代owner/public-contract裁決。

## Exact write set

- `ui_react/src/tests/form_management_entry_readiness.test.tsx`（new）
- `tests/test_react_form_management_entry_readiness.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-form-management/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`readiness-candidate`，不得標cutover／replacement／active。

若人工決定建立dedicated page，`ui_react/src/pages/FormManagementPage.*`、`src/api/form_management/`及
`src/adapters/form_management/`必須另立production successor，不能擴張進本包。

## 必要門

1. template library、contract management、questionnaire/resume與statistics逐項裁決owner/SSOT/PII/document boundary。
2. Phase5A另行凍結dedicated React identity或明確one-to-many replacement；未完成固定
   `BLOCKED_MISSING_REACT_SURFACE`。
3. raw template/form/document payload不得進React；existing partial actions保持disabled。
4. `/?entry=form-management`保留且可精確rollback；沒有dedicated page時不得標candidate replacement。
5. registry validator、readiness tests、UTF-8、diff與Part 00 scenario inventory通過。

`BLOCKED_MISSING_REACT_SURFACE`是本包terminal expected result；本包不得將readiness tests通過寫成candidate、
不得建立one-to-many推論，也不得新增production identity/page。真Chrome只驗legacy exact rollback與unknown
route fail closed。Queue/manifest/readiness只由Integration Owner更新。

DB：未核准Scope BLOCKED；核准後docs/readiness Scope/Change inventory PASS，其他NOT_RUN；`DB_CHANGE_NOT_READY`。
