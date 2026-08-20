---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-system-status-query
date: 2026-08-17
owner: Global Runtime / Entry Governance Integration Owner
domain: Global Runtime
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase5-system-status-entry-identity-amendment PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
approval_required: 核准此 exact Phase 5 System Status Entry Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：System Status query entry candidate工作包

## Activation

本包不再兼任identity amendment。必須先完成獨立
`PROV-20260817-react-admin-phase5-system-status-entry-identity-amendment-work-package.md`，並在latest HEAD
fresh-read其registry receipt；否則固定`BLOCKED_MISSING_SYSTEM_STATUS_IDENTITY`。

## Identity decision

Streamlit `ui:08_system_status.py`／rollback key `system-status`；新增React identity
`ui-react:#system-status`。現有Shell badge不是完整entry，`#account-management`也不得冒充replacement。

## Exact write set

- `ui_react/src/tests/system_status_entry_cutover.test.tsx`（new）
- `tests/test_react_system_status_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-system-status-query/`（new receipts）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`query-candidate`，不得標cutover／replacement／active。

queue、manifest、readiness matrix與receipt只由Primary Integration Writer修改；本包不得修改page／client／router。

## Gates

G0 Phase5A/B及identity amendment fresh receipts、exact candidate approval；actual navigation switch approval只屬
另行核准的per-entry switch successor；G1 identity/route/queue/
rollback及independent expected manifest一致；G2 typed snapshot/auth/request budget；
G3 8000/8501/5173 dual-run；G4真TOTP Chrome Network→DOM/reload/session expiry；G5同snapshot雙UI；
G6 `/?entry=system-status` rollback與unknown fail closed；G7 tests/build/lint/UTF-8/diff；G8只能標candidate，
不能retire source。TCP open、Shell badge、build pass都不是entry evidence。
Page/Shell任何hardcoded online、latency、count或成功fallback固定fail closed；query-only forward-data明列
`not-applicable`。Queue、manifest與readiness只由Integration Owner更新，entry writer不得自行標READY。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（0 DB write），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
