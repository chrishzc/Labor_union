---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-line-query
date: 2026-08-17
owner: LINE / Entry Governance Integration Owner
domain: Customer Service / LINE Identity / LINE Configuration
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase3a-browser-closure PASS; PROV-20260816-react-admin-phase4c-line-rules-rich-menu-query PASS; PROV-20260817-line-knowledge-authorization-normalization PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 LINE Query Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：LINE Management query entry candidate工作包

## Identity/scope

Streamlit `ui:07_line_management.py`／rollback `line-management`／React `ui-react:#line-management`。六tabs保留，
只驗Customer Service/Identity query與Rules/Rich Menu四GET。Delivery/Knowledge與所有provider/mutation維持鎖定。

## Exact write set

- `ui_react/src/tests/line_management_entry_cutover.test.tsx`（new）
- `tests/test_react_line_management_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-line-query/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`query-candidate`，不得標cutover／replacement／active。

Production page/client不在本candidate包。Delivery/Knowledge需先完成4C-D/K H+R successors。

## Gates

G0 prerequisites/exact approval；G1 registry/rollback；G2 auth/schema/PII/request budget；G3 dual-run；G4真TOTP
browser六tabs/query/reload/expiry；G5controlled configuration雙UI；G6 rollback；G7 full tests/build/lint/UTF-8/diff；
G8只標query candidate。禁止raw task/content、provider send、publish/save/delete/retry假成功與用真provider驗收。
六tabs逐一建立control matrix與oracle；Network必須證明0 POST/PATCH/DELETE/provider call。Current客服／Identity
mutation若仍可達且未具Phase3A真browser receipt，固定BLOCKED，不能靠「本包不測」略過。Query-only部分的
forward-data明列`not-applicable`；Queue/manifest/readiness只由Integration Owner更新。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（0 DB write），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
