---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-orders-query
date: 2026-08-17
owner: Orders / Entry Governance Integration Owner
domain: Orders
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation PASS
conditional_prerequisites: PROV-20260816-react-admin-phase2b-orders-safe-mutations when any mutation is reachable
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Orders Query Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Orders query entry candidate工作包

## Replacement group

Streamlit `ui:02_orders.py`／rollback `orders`，對應兩個React identities：`ui-react:#orders`與
`ui-react:#order-tracker`。兩者必須各有route/evidence，不能壓成一個模糊identity。

G0 必須以 `PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation` 的 fresh PASS
取代舊Phase2A完成假設；現行raw/unapproved query drift未移除前固定BLOCKED。Phase2B只有在任何mutation可達時
才是hard prerequisite，否則所有mutation必須native disabled且Network 0 non-GET。

## Exact write set

- `ui_react/src/tests/orders_entry_cutover.test.tsx`（new）
- `ui_react/src/tests/order_tracker_entry_cutover.test.tsx`（new）
- `tests/test_react_orders_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-orders-query/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`query-candidate`，不得標cutover／replacement／active。

不得在本包修改Orders pages/clients或啟用Phase2B mutations；發現contract gap回到原successor。

## Gates

G0 prerequisites/exact approval；G1 one-to-two identities/rollback；G2 approved GET/request budget/PII；G3 dual-run；
G4真TOTP browser list→drawer→tracker/reload/expiry；G5同case server facts雙UI；G6 rollback；G7 full tests/build/
lint/UTF-8/diff；G8只標query candidate。7-stage、SOP、LINE、推薦、三結清無lineage時unavailable；禁止
`order_status`、日期或金額推導。Phase2B reopen/service-date若在此entry可達，必須先有其fresh真browser／
controlled-data receipt；否則由正式feature gate原生disabled且Network 0 non-GET，不能只由test假設disabled。
兩個React identities各自具有registry、route、same-case及rollback receipt；Queue/manifest/readiness只由
Integration Owner更新。Query-only forward-data明列`not-applicable`。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（query candidate 0 DB write），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
