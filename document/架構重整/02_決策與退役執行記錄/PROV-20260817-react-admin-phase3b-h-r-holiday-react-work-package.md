---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase3b-h-r-holiday-react
date: 2026-08-17
owner: Scheduling / React
domain: Scheduling
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3b-h-holiday-public-contract-uow PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS; PROV-20260817-react-admin-phase3b2-r-leave-substitution-react PASS
approval_required: 核准此 exact Phase 3B-H-R Work Package
approval_authority: 使用者於 2026-08-21 明確核准 exact Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3b-h-r-holiday-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3B-H-R：Holiday React Query／Preview／Apply接線工作包

## Scope

Browser/DOM驗收只能使用`validation/scenarios/react_admin_holiday_policy.json`與
`validation/ui_business_workflows/part_09_scheduling/`；component fixture不得代替。

在既有SchedulingPage「國定假日政策」tab與原Drawer位置接Phase3B-H Query→Preview→Apply→receipt→re-query。
不重畫頁面、不啟用leave/quick-lock/actual-start等其他mutation。

## Exact write set

- `ui_react/src/api/scheduling/holiday_schemas.ts`（new）
- `ui_react/src/api/scheduling/holiday_errors.ts`（new）
- `ui_react/src/api/scheduling/holiday_client.ts`（new）
- `ui_react/src/adapters/scheduling/holiday_flow_adapter.ts`（new）
- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/SchedulingPage.css`
- `ui_react/src/tests/fixtures/holiday_contract_fixtures.ts`（new）
- `ui_react/src/tests/holiday_client.test.ts`（new）
- `ui_react/src/tests/holiday_adapter.test.ts`（new）
- `ui_react/src/tests/scheduling_holiday_flow.test.tsx`（new）
- `ui_react/src/tests/scheduling_no_fake_mutation.test.tsx`

`SchedulingPage.tsx`是shared hot spot；本包Presentation Writer必須是同批唯一writer，其他Scheduling lanes先freeze。

## Acceptance

0. G0須引用Phase3B2-R的fresh PASS receipt、page/CSS/no-fake test baseline與current base ref；兩者不一致或
   同批另有Scheduling presentation writer固定`BASE_DRIFT`，不得施工。
1. strict Zod typed Query/Preview/Receipt；server-required欄位不可optional/default，未知extra fail closed。
2. discriminated union狀態機；Apply前reason、fingerprint、expected version與planning horizon齊全。
3. apply_pending原生disabled；timeout/503進outcome_unknown，只有相同payload與Idempotency-Key可retry。
4. receipt後必re-query；只有observed才顯示成功。cache/observation失敗不得改寫receipt為失敗。
5. UI不推導雙倍薪、結束日、coverage或eligibility；server candidate以外不可選。
6. 其他Scheduling controls維持native disabled，0 alert/confirm/prompt/local business mutation。
7. 真TOTP browser與controlled holiday scenario覆蓋stale/replay/conflict/rollback；Phase5 cutover另案。

DB：Scope PASS（UI only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

## 2026-08-22 integration result

React strict client、adapter state machine、既有Scheduling tab接線、focused 14 tests、production build及
owned disposable MySQL Chrome Query→Preview→Apply→receipt→re-query均已完成；receipt在post-Apply re-query後
維持可見，owned DB已刪除且原development 8000／既有DB GET已恢復。

Canonical scenario drift已由
`PROV-20260822-react-admin-phase3b-h-r-holiday-mutation-scenario-lineage-successor-work-package.md`改為revision 2
controlled mutation lineage；此項metadata blocker已解除。browser stale／conflict／rollback variants仍為`NOT_RUN`，
故本包維持`blocked`，不得作為Phase 5 scheduling cutover的PASS prerequisite。

2026-08-22 controlled follow-up已完成stale typed DOM、rollback zero-partial readback、same-key browser replay
及conflicting-draft pre-transport guard。最終controlled run另以臨時Vite pre-transform固定UUID，production source、
HTTP request body與response均未修改；同一UI先成功Apply，再以同key／不同payload送出，真FastAPI回409，DOM進入
`conflict`並顯示`idempotency_key_conflict`。MySQL readback證明winner row保留、該key只有一筆receipt，owned DB已
精準刪除，current 8000／5174與既有DB GET均恢復。依本遷移計畫的最新人工裁決，本機UI可採development auth
bypass，故true-TOTP標為`NOT_RUN_ACCEPTED_DEVELOPMENT_BYPASS`，不得冒充執行。本包runtime acceptance完成；
Phase 5 scheduling cutover仍須通過其獨立entry gate。
