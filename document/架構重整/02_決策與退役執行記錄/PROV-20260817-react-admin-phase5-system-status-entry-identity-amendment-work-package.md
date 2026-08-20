---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-system-status-entry-identity-amendment
date: 2026-08-17
owner: Global Runtime / Entry Governance Integration Owner
authority: awaiting-exact-human-approval-and-phase5a-completion
approval_required: 核准此 exact Phase 5 System Status Entry Identity Amendment Work Package
prerequisites: PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS
prerequisite_rule: every listed prerequisite needs fresh PASS evidence; old receipt or document existence is insufficient
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: captured-before-writer
base_drift_rule: stop-and-refreeze-on-head-queue-manifest-or-registry-drift
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 5：System Status React entry identity amendment工作包

## Scope

在latest Phase5A registry revision上新增canonical `ui-react:#system-status`、dedicated page與source witnesses。
本包不切navigation、不改Streamlit source、不把Shell badge當page，也不宣稱entry candidate。

不得以「第12個」作identity authority；開工時須fresh-read latest registry、未追蹤paths與collision inventory。

## Exact write set

- `document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md`
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `validation/scenarios/react_admin_entrypoints.json`
- `ui_react/src/pages/SystemStatusPage.tsx`（new）
- `ui_react/src/pages/SystemStatusPage.css`（new）
- `ui_react/src/App.tsx`
- `ui_react/src/components/MasterLayout.tsx`
- `ui_react/src/api/system/system_status_client.ts`
- `ui_react/src/tests/system_status_entry_identity.test.tsx`（new）
- `ui_react/src/tests/react_entrypoint_registry.test.ts`
- `tests/test_entrypoint_review_queue.py`
- `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl`
- 本工作包、`02` README、主React計畫與identity receipt（Integration Owner only）

## Gates

| Gate | PASS condition |
|---|---|
| G0 | Phase5A PASS receipt、exact approval、latest collision inventory |
| G1 | canonical route/owner/scenario/source witnesses與independent manifest revision一致 |
| G2 | dedicated page與所有可見Shell status surfaces只顯示typed snapshot；MasterLayout不得optimistic online、硬編通知數／principal或API失敗後成功fallback |
| G3 | App/NAV/PAGE_SECTION_MAP/duplicate navigation registry exact一致；prototype hashes fail closed |
| G4 | auth guard、reload/new-tab/unknown hash component tests；不切navigation或source status |
| G5 | queue只新增review_required identity；不得標active/replacement/cutover-ready |
| G6 | focused/full tests、build/lint、UTF-8/diff/secret scan通過 |

## DB gate

0 DB change。未核准Scope BLOCKED；核准後Scope/Change inventory PASS，其餘NOT_RUN；
`DB_CHANGE_NOT_READY`。
