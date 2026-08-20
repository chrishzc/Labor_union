---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3b2-r-leave-substitution-react
date: 2026-08-17
owner: Scheduling React Integration Owner
domain: Scheduling
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase3b2-leave-substitution-contract-outer-uow PASS; PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment PASS; PROV-20260817-react-admin-phase3b-q-r-scheduling-current-query-react PASS
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 3B2-R Leave/Substitution React Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Phase 3B2-R：Leave／Substitution React 接線工作包

## 0. Scope

Browser/DOM驗收只能使用`validation/scenarios/react_admin_leave_substitution.json`與
`validation/ui_business_workflows/part_09_scheduling/`；component fixture不得代替。

在既有`SchedulingPage`「突發請假代班」tab與原Resolution workbench位置接入正式
Query→Preview→Apply→receipt→re-query。保留代班／順延兩種選項與既有資訊層級；不重畫頁面，不啟用
quick lock、actual-start、custom-rest、leave-intake review或其他mutation。

本包只能在Phase3B2 backend single-outer-UoW與Phase3B1 Staff selector都有fresh PASS後核准／施工。

## 1. Exact write set

- `ui_react/src/api/scheduling/leave_substitution_schemas.ts`（new）
- `ui_react/src/api/scheduling/leave_substitution_errors.ts`（new）
- `ui_react/src/api/scheduling/leave_substitution_client.ts`（new）
- `ui_react/src/adapters/scheduling/leave_substitution_flow_adapter.ts`（new）
- `ui_react/src/adapters/scheduling/leave_substitution_flow_store.ts`（new）
- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/SchedulingPage.css`
- `ui_react/src/tests/fixtures/scheduling/leave_substitution_contract_fixtures.ts`（new）
- `ui_react/src/tests/leave_substitution_client.test.ts`（new）
- `ui_react/src/tests/leave_substitution_adapter.test.ts`（new）
- `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx`（new）
- `ui_react/src/tests/scheduling_no_fake_mutation.test.tsx`
- `validation/scenarios/react_admin_leave_substitution.json`（new）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3b2-r-leave-substitution-react/`（Integration Owner only）

`SchedulingPage.tsx`與CSS是shared hot spot；本包同批只能有一位Presentation Writer。禁止修改shared
transport/Auth、package/lockfile、backend、DB、其他pages或Phase3B1 bounded clients。

## 2. Public-client contract

1. allowlist只有Phase3B2凍結的assignments Query、Preview與Apply routes；每次request即時取得memory token。
2. success envelope、impact、linked request、receipt與typed error均strict decode；禁止raw dict、unsafe cast與
   message字串分支。
3. Preview只使用server提供的assignment/version/date/candidate；UI不計算延長日、buffer、薪資、帳務或eligibility。
4. Apply送出expected versions、preview fingerprint、trim後1–500 reason、correlation及stable idempotency key。
5. `202`或LINE task intent不是成功；只有terminal receipt收到後完成re-query並觀察到server projection才顯示成功。

## 3. Presentation state machine

`idle → query_loading → query_ready → preview_loading → preview_ready → apply_pending → receipt_received →
requery_loading → observed`。另有`typed_error | stale | outcome_unknown | observation_failed`，互斥render。

- draft變動立即失效舊Preview；Apply pending時所有會改payload／關閉workbench的控制native disabled。
- timeout/network/503才可進`outcome_unknown`，且只以相同payload與Idempotency-Key重試。
- conflict/stale只能重新Query／Preview；不得自動Apply。
- receipt後re-query失敗保留receipt並顯示observation failure，不得改稱Apply失敗。
- linked leave request只顯示server回傳狀態；LINE delivery intent不得冒充通知已送達。

## 4. Acceptance／anti-fake gates

0. G0須引用Phase3B-Q-R的fresh PASS receipt、page/CSS/no-fake test baseline與current base ref；兩者不一致或
   同批另有Scheduling presentation writer固定`BASE_DRIFT`，不得施工。
1. 原四tabs、甘特、Holiday、Inbox與precision Drawer槽位仍存在；只有本workbench取得核准non-GET。
2. 所有其他mutation controls維持exact stable ID、native disabled、0 handler、0 alert/confirm/prompt。
3. client negative tests覆蓋missing/extra/wrong/null、401/403/404/409/422/503、abort與token切換。
4. flow tests覆蓋Preview零樂觀更新、double-submit、stale、same-key unknown retry、receipt re-query與partial-tab error。
5. 真TOTP browser使用Part00去敏controlled case，保存Network→DOM與server receipt；component fixture不得替代。
6. backend disposable MySQL atomicity receipt只引用Phase3B2 fresh evidence，不能由browser測試代替。

## 5. DB gate

未核准Scope `BLOCKED`；核准後Scope／Change inventory `PASS`（UI-only、0 DB write），其餘`NOT_RUN`；
結論固定`DB_CHANGE_NOT_READY`。
