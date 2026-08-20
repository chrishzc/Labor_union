---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-cutover-scheduling
date: 2026-08-17
owner: Scheduling / Entry Governance Integration Owner
domain: Scheduling
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS; PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS; PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow PASS; PROV-20260817-react-admin-phase3b-q-r-scheduling-current-query-react PASS; PROV-20260817-react-admin-phase3b2-r-leave-substitution-react PASS; PROV-20260817-react-admin-phase3b-h-holiday-public-contract-uow PASS; PROV-20260817-react-admin-phase3b-h-r-holiday-react PASS
actual_switch_prerequisite: PROV-20260817-react-admin-phase5-entry-navigation-switch-decision PASS plus a separately approved exact per-entry switch successor
delivery_ceiling: entry-readiness-candidate-only
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; approval or old receipt alone is insufficient
approval_required: 核准此 exact Phase 5 Scheduling Entry Work Package
authority: awaiting-exact-human-approval
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：Scheduling entry readiness／query candidate工作包

## Identity與範圍

Streamlit `ui:03_calendar.py`／rollback `scheduling`／React `ui-react:#scheduling`。`#staff`與`#orders`
只能是deep-link，不是本entry replacement。production Scheduling page/client不在本candidate write set；未完成能力
回到Phase3B successor。

## Exact write set

- `ui_react/src/tests/scheduling_entry_cutover.test.tsx`（new）
- `tests/test_react_scheduling_entry_cutover.py`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`（Integration Owner only；其他lane唯讀）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-readiness/entry-readiness-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase5-entry-cutover-scheduling/`（new）

`validation/scenarios/react_admin_entrypoints.json`是Phase5A凍結輸入，不在本包write set；預期改動即
`BLOCKED_EXPECTED_MANIFEST_MUTATION`。本包最高只能標`query-candidate`，不得標cutover／replacement／active。

## 必要門

1. Phase3B1 selector、Phase3B2 single outer-UoW、Phase3B2-R Leave React、Phase3B-Q-R current calendar query、
   Phase3B-H Holiday hardening與Phase3B-H-R React接線均完成。
2. calendar／leave／holiday／matching逐欄與control-ID matrix凍結；同case/staff/month在雙UI一致。
3. 禁止React推導日期、buffer、payroll、coverage、eligibility；禁止`alert/confirm/prompt`與local success。
4. Leave／Holiday／Actual-start／quick-lock未取得各自核准前保持native disabled，且0 unexpected non-GET。
5. 真TOTP browser覆蓋月份切換、Drawer、empty、abort、stale、conflict、session expiry與rollback。
6. 只能標`query-candidate`或明確partial；`/?entry=scheduling`可精確返回舊頁。

Current page任何`MOCK_STAFF`／`MOCK_ORDERS`、embedded schedule、local date/extension公式、
`alert/confirm/prompt`或local success固定`BLOCKED_MOCK_REMAINDER`；因本包不能改production page/client，命中
即不得標candidate。所有未核准controls native disabled且Network 0 non-GET；Query forward-data為N/A。
Queue/manifest/readiness只由Integration Owner更新。

DB：未核准Scope BLOCKED；核准後Scope/Change inventory PASS（candidate包0 DB write），其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
