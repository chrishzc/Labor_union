---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-anomalies-query
date: 2026-08-17
owner: Anomalies / Entry Governance Integration Owner
domain: Anomalies
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase2d-h-closure-gate-amendment PASS; PROV-20260817-react-admin-phase2d-query-browser-closure PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Anomalies Query Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Anomalies query entry candidate工作包

## Identity/scope

Streamlit `ui:06_finance_alerts.py`／rollback `anomalies`／React `ui-react:#anomalies`。只驗證
Anomalies summary與Import Warning task兩個GET；Claim/Resolve/recovery/transition保持disabled。

## Exact write set

- `ui_react/src/tests/anomalies_entry_cutover.test.tsx`（new）
- `tests/test_react_anomalies_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-anomalies-query/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`query-candidate`，不得標cutover／replacement／active。

Production page/client不在本candidate包；若需修正則先回到Phase2D/3D successor，不得順手改。

## Gates

G0 prerequisites/exact approval；G1 registry/rollback identity；G2 schema/auth/PII/request budget；G3 dual-run；
G4真TOTP browser success/empty/error/401/403/reload；G5controlled anomaly/warning雙UI可觀察；
G6 `/?entry=anomalies` rollback；G7 focused/full tests、UTF-8/diff/secret；G8只標query candidate。
禁止前端推severity/KPI、non-GET、假Resolve或把query candidate當完整replacement。
Network必須證明0 POST/PATCH/DELETE，Claim/Resolve/recovery無local state transition或success提示；此query-only
entry的forward-data明列`not-applicable`。Queue/manifest/readiness只由Integration Owner更新。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（0 DB change），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
