---
doc_type: work-package
declared_status: blocked
identity: PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment
date: 2026-08-16
owner: Integration Owner
domain: Staff / Scheduling Staff Matching Profile
subsystem: Staff Selector / Preferences / Availability / Lifecycle / React Presentation
specification: PROV-20260816-react-admin-phase3b-staff-scheduling-safe-actions-specification
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS
activation_state: blocked-prerequisites
approval_required: 核准此 exact Phase 3B1 Amendment
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
---

# Phase 3B1：Staff public contract hardening 與 selector 修訂工作包

## 0. 為何需要重新核准

Phase3B G1 fresh audit證明原exact write set不可施工：React沒有canonical Staff selector client；Preferences
及Lifecycle錯誤契約未typed；Availability尚未證明使用正式shared occupancy mutex。依原核准包不得自行新增
backend production或Staff client，所以原Phase3B維持blocked。

使用者已於2026-08-17明確回覆：

> 核准此 exact Phase 3B1 Amendment

本修訂已取得授權，但仍受Scenario Lineage與Global Error Boundary activation gate約束；此核准不包含
Leave/Substitution，其raw impact DTO與第二段UoW由獨立3B2工作包承接。

## 1. Scope

Controlled input固定來自`validation/scenarios/react_admin_staff_safe_actions.json`與其fixture/expected
lineage；production writer只讀。缺少時固定`PHASE3_SCENARIO_LINEAGE_NOT_READY`。

1. `GET /api/v1/staff/summaries` 加入既有internal session guard，維持bounded cursor contract；
2. 建立React Staff selector bounded client／adapter；
3. Preferences route errors收斂為現有Global typed error payload，補route tests；
4. Availability Apply使用`lock_staff_occupancy_mutex`或由測試證明現有鎖定與正式shared mutex完全等價；
5. Lifecycle schema strict、fingerprint 64-hex、typed errors與route tests；
6. 啟用StaffPage preferences、availability create/cancel、retirement/reactivation三組flow。

本修訂不把既有 route「有回應」視為契約已完成。Backend contract 必須先 freeze 並通過 focused
route／workflow tests，React production writer 才能開工；任何一條 flow 未閉合時只阻擋該 flow，
不得以其他 flow 測試全綠宣稱整包完成。

Current activation固定`BLOCKED_PREREQUISITES`：Scenario Lineage metadata已於2026-08-17完成，但Global
Error Boundary仍因correlation precedence裁決而未PASS。scenario、catalog、fixture、expected與receipt manifest
已存在；Global未PASS前仍不得啟動backend或React writer，approval本身不繞過activation gate。

## 2. Exact backend write set

- `api/routes/staff.py`
- `api/schemas/staff_summary.py`
- `api/routes/staff_matching_preferences.py`
- `api/schemas/staff_matching_preferences.py`
- `subsystems/scheduling/staff_matching_preference_workflow.py`
- `infrastructure/mysql/staff_matching_preference_repository.py`
- `api/routes/staff_availability.py`
- `api/schemas/staff_availability.py`
- `api/dependencies/staff_availability.py`
- `subsystems/scheduling/staff_availability_workflow.py`
- `api/routes/staff_retirement.py`
- `api/schemas/staff_retirement.py`
- `subsystems/staff/retirement_workflow.py`
- `infrastructure/mysql/staff_availability_repository.py`
- `tests/test_staff_and_scheduling_bounded_query_migration.py`
- `tests/test_staff_summary_routes.py`（新增）
- `tests/test_staff_matching_preferences.py`
- `tests/test_staff_matching_preferences_workflow.py`
- `tests/test_staff_matching_preferences_routes.py`（新增）
- `tests/test_staff_matching_preferences_disposable_mysql_e2e.py`（新增）
- `tests/test_staff_availability_routes.py`
- `tests/test_staff_availability_workflow.py`
- `tests/test_staff_availability_transaction_boundary.py`（新增）
- `tests/test_staff_availability_mysql_contract.py`
- `tests/test_staff_availability_disposable_mysql_e2e.py`（新增）
- `tests/test_staff_retirement_workflow.py`
- `tests/test_staff_retirement_routes.py`（新增）
- `tests/test_staff_retirement_consumer_guards.py`
- `tests/test_staff_retirement_disposable_mysql_e2e.py`（新增）
- `tests/test_react_phase3b_public_contracts.py`（新增）

不得修改DB/schema/migration/shared exception handler或正式Domain規則。若Global typed error無法只在route
boundary收斂，停止並回`SHARED_HOTSPOT_REQUIRED`。

Backend freeze 必須另證明：

- Staff summaries 受既有 internal session guard 保護，`staff_id` 與 `after_id` 互斥錯誤不再以 raw detail
  穿透；
- Preferences 的 404／409／422 business error 使用既有 Global typed error payload；FastAPI 在 route
  之前產生的 request-validation 422 不得被冒充為本包已全面收斂；
- Availability Apply 的 fresh lock path 實際使用 canonical `lock_staff_occupancy_mutex`，並以真實
  repository／workflow evidence 證明 assignment、waiting lock 與 buffer collision 都在同一 mutex
  邊界內；只鎖 `staff` row 不算等價；
- Lifecycle 拒絕無 timezone 的 `effective_at`，query／preview／receipt schema `extra="forbid"`，
  fingerprint 僅接受 64 位小寫 hexadecimal；route 同時收斂 `ValueError` 與 domain 可能拋出的
  `TypeError`，不得把輸入錯誤轉成 500；Apply 使用獨立 receipt view，不把 receipt 偽裝成 query view。

### 2.1 Fresh-audit mandatory additions

- 本節取代上文「route 之前的 422 未全面統一」的容許：Phase3B1 只能在
  `PROV-20260817-global-fastapi-typed-error-boundary` PASS 後施工，request-validation/auth 錯誤也必須
  符合 Global envelope。
- Preferences 在 profile row 尚未存在時也必須鎖定穩定 aggregate identity，並以真
  MySQL two-connection concurrent create 證明不會 lost update。Apply須先鎖staff aggregate，再讀profile／
  values與receipt；取得鎖後重新查receipt。same fingerprint回原receipt，不同fingerprint為typed conflict。
- Preferences canonical command fingerprint必含`expected_version`與`preview_fingerprint`；Availability及
  Lifecycle fingerprint必含`preview_fingerprint`。漏任一submitted field皆不得稱same-payload replay。
- Availability workflow/repository 不得 hidden commit/rollback；commit owner 只能是唯一 outer
  `MySqlUnitOfWork`。Apply在同一UoW內先呼叫
  `lock_staff_occupancy_mutex(cursor, [staff_id])`，取得mutex後重新查receipt，再讀aggregate/version、blocks、
  assignment、waiting lock與buffer。Repository不得暴露或呼叫commit/rollback；只鎖`staff` row不算等價。
- Lifecycle Apply使用獨立strict`StaffLifecycleApplyReceiptView`，至少含`staff_id/state/resulting_version/
  preview_fingerprint/idempotency_key`；不得再以query view冒充receipt。
- MySQL E2E 若 skip，G2 固定 `BLOCKED_ENGINE_EVIDENCE`，不得以 route/workflow unit tests 取代。

## 3. Exact frontend delta

本修訂的frontend exact write set完整列示如下，不依賴讀者回查原Phase3B lane：

- `ui_react/src/api/staff_preferences/staff_preferences_schemas.ts`
- `ui_react/src/api/staff_preferences/staff_preferences_errors.ts`
- `ui_react/src/api/staff_preferences/staff_preferences_client.ts`
- `ui_react/src/adapters/staff/staff_preferences_adapter.ts`
- `ui_react/src/tests/fixtures/staff/staff_preferences_contract_fixtures.ts`
- `ui_react/src/tests/staff_preferences_client.test.ts`
- `ui_react/src/tests/staff_preferences_adapter.test.ts`
- `ui_react/src/api/staff_availability/staff_availability_schemas.ts`
- `ui_react/src/api/staff_availability/staff_availability_errors.ts`
- `ui_react/src/api/staff_availability/staff_availability_client.ts`
- `ui_react/src/api/staff_lifecycle/staff_lifecycle_schemas.ts`
- `ui_react/src/api/staff_lifecycle/staff_lifecycle_errors.ts`
- `ui_react/src/api/staff_lifecycle/staff_lifecycle_client.ts`
- `ui_react/src/adapters/staff/staff_availability_adapter.ts`
- `ui_react/src/adapters/staff/staff_lifecycle_adapter.ts`
- `ui_react/src/tests/fixtures/staff/staff_availability_contract_fixtures.ts`
- `ui_react/src/tests/fixtures/staff/staff_lifecycle_contract_fixtures.ts`
- `ui_react/src/tests/staff_availability_client.test.ts`
- `ui_react/src/tests/staff_lifecycle_client.test.ts`
- `ui_react/src/tests/staff_availability_lifecycle_adapter.test.ts`
- `ui_react/src/pages/StaffPage.tsx`
- `ui_react/src/pages/StaffPage.css`
- `ui_react/src/tests/staff_page_real_data.test.tsx`
- `ui_react/src/tests/staff_preferences_flow.test.tsx`
- `ui_react/src/tests/staff_availability_flow.test.tsx`
- `ui_react/src/tests/staff_lifecycle_flow.test.tsx`
- `ui_react/src/tests/staff_no_fake_mutation.test.tsx`
- `ui_react/src/tests/staff_request_budget.test.tsx`
- `ui_react/src/tests/staff_control_contract.test.tsx`

另新增Staff selector bounded slice：

- `ui_react/src/api/staff_directory/staff_directory_schemas.ts`
- `ui_react/src/api/staff_directory/staff_directory_errors.ts`
- `ui_react/src/api/staff_directory/staff_directory_client.ts`
- `ui_react/src/adapters/staff/staff_directory_adapter.ts`
- `ui_react/src/tests/fixtures/staff/staff_directory_contract_fixtures.ts`
- `ui_react/src/tests/staff_directory_client.test.ts`
- `ui_react/src/tests/staff_directory_adapter.test.ts`

SchedulingPage與Leave/Substitution Lane D/F固定不施工。StaffPage不可import`mockData`或其他page-local staff literal。

四個 frontend bounded clients 必須在每次 request 當下讀取 current memory session token；無 token 時
零 fetch。Success envelope 與 nested DTO 均 strict decode，禁止 `z.any`、`z.record`、`.default()`、
`.passthrough()`、`.catch()`、`.coerce()`、`.transform()`、`as any` 與 `unknown as`。Preferences
Apply 必須送出 server Query 的完整 profile snapshot 加上使用者修改，不得只送單欄 patch。

### 3.1 Frozen frontend field contract

- `staff_directory`：只接`GET /api/v1/staff/summaries`；item僅`id>0/name nullable/phone nullable`，
  page僅`items/next_cursor nullable`。Adapter不得補年資、區域、證照、在職、技能或銀行。
- `staff_preferences`：definition/profile/preview/apply/receipt逐欄strict；Apply body必須來自
  server Query的完整profile snapshot。本UI只啟用`preferred_service_days`與
  `daily_service_hours`；cooking skills/special notes不屬此aggregate，原位readonly/unavailable。
- `staff_availability`；UI只啟用`create_long_leave/create_pause/cancel`；block/action/version/
  fingerprint/receipt由server決定。Adapter不得算day count、overlap、buffer、eligibility或
  `createdAt`；日數槽顯示`—`。
- `staff_lifecycle`；state僅`active|retired`，`effective_at`必須aware ISO，action僅
  `retirement|reactivation`；Apply回獨立receipt含server fingerprint。Reactivation不恢復舊facts。
- 四client每次request當下讀memory token；無token零fetch。Success/nested strict，禁止
  `z.any/z.unknown/z.record/default/passthrough/catch/coerce/preprocess/transform/as any/unknown as`。

### 3.2 Request budget and state machine

- directory initial 1 GET；next page每次1 GET；deep-linked exact staff最多1 GET。
- preferences：definitions GET1 + profile GET1 + preview POST1 + apply POST1 + requery GET1；definitions
  已緩存時最多4。
- availability create/cancel：blocks GET1 + preview POST1 + apply POST1 + requery GET1。
- lifecycle：query GET1 + preview POST1 + apply POST1 + requery GET1。
- 禁止StrictMode double fetch、background poll與Drawer burst；selection變更abort/generation-discard stale response。
- mutation只能使用exhaustive union：`idle → query_loading → query_ready → editing →
  preview_loading → preview_ready → apply_pending → receipt_received → requery_loading →
  observed`。Edit invalidates preview；409→`stale`；Apply timeout/network/503→`outcome_unknown`，
  僅此狀態可同payload/key retry；requery失敗→`observation_failed`。

### 3.3 Stable controls and unavailable slots

必須保留/建立：`staff.page`、`staff.tab.roster/preferences/unavailability`、
`staff.preferences.preview/apply`、`staff.availability.create.preview/apply`、
`staff.availability.cancel.preview/apply`、`staff.lifecycle.retirement.preview/apply`、
`staff.lifecycle.reactivation.preview/apply`。

必須native disabled：`staff.master.create/edit/save/attachment-upload/bank-edit/certificate-approve`、
`staff.preferences.cooking-skills`、`staff.preferences.special-notes`。Roster的履歷、證照、銀行與新增
槽保留視覺並明示unavailable；不得用directory三欄冒充Staff master。

`StaffPage.tsx/.css`只有一位Presentation writer。`SchedulingPage.tsx/.css`、
`ui_react/src/api/mockData.ts`不得修改或刪除；StaffPage只移除自己的mock import。

StaffPage必須移除自己的`MOCK_STAFF`依賴、所有local business mutation、`alert()`／`confirm()`、以
`Date.now()`產生availability identity及literal staff business facts；page不得direct fetch，只能composition
四個bounded clients。`staff.availability.end-pause`本包保持native-disabled/unavailable，其正式React接線與
preference definition administration已記錄於
`PROV-20260817-react-admin-phase3b1-staff-remaining-controls-gap.md`。

Staff summaries deep-link查無`staff_id`沿用server成功empty page，React顯示明確「找不到人員」empty state，
不得改推404或選第一筆。Directory client另須拒絕duplicate IDs、non-forward cursor及已看過的
`next_cursor`，禁止自動重試。

Definition mutation routes不屬本包；只允許讀definitions以編輯staff profile，不得以profile tests宣稱
definition administration已hardening。

## 4. Gates

沿用Phase3B G0–G8，但只驗Staff selector、Preferences、Availability、Lifecycle。G2額外要求：

- Staff summaries 401/disabled principal、cursor/duplicate/repeated-cursor fail closed；
- Preferences strict error/status route coverage；
- Availability shared occupancy mutex、overlap、waiting-lock、buffer、replay、stale、append-only cancel；
- Lifecycle strict extra/missing/wrong/fingerprint、retired consumer guards、reactivation不恢復舊facts。

Presentation gate 另要求：receipt received 與 observed 分離；re-query 失敗顯示
`observation_failed`，不得稱 Apply 失敗；只有 timeout／network／503 的 `outcome_unknown` 可以用同一
Idempotency-Key 與完全相同 payload 重試。Availability 不得在前端計算 overlap、天數、buffer 或
eligibility；Lifecycle control 只依 server state 顯示。

G7只可在去敏disposable staff IDs執行；不得對營運Staff退役或建立不可服務期間。缺安全資料時狀態為
`blocked-controlled-data`，不得以mock browser宣稱完成。

G1 contract matrix必須逐endpoint／failure凍結：HTTP status、category、public code、retryable、
current_version、domain_blockers與frontend transition。至少涵蓋`staff_unavailability_overlap`、
`staff_unavailability_assignment_conflict`、`staff_unavailability_waiting_lock_conflict`、
`staff_unavailability_buffer_conflict`、`staff_not_found`、`preference_definition_not_active`；UI/test禁止依
中文message或raw`ValueError`文字分支。Availability correlation不得使用固定
`staff-availability-query`，必須遵守Global `X-Correlation-ID`契約。

## 5. Required commands and evidence

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .pytest_tmp\phase3b1 -q `
  tests\test_staff_and_scheduling_bounded_query_migration.py `
  tests\test_staff_summary_routes.py `
  tests\test_staff_matching_preferences.py `
  tests\test_staff_matching_preferences_workflow.py `
  tests\test_staff_matching_preferences_routes.py `
  tests\test_staff_matching_preferences_disposable_mysql_e2e.py `
  tests\test_staff_availability_routes.py `
  tests\test_staff_availability_workflow.py `
  tests\test_staff_availability_transaction_boundary.py `
  tests\test_staff_availability_mysql_contract.py `
  tests\test_staff_availability_disposable_mysql_e2e.py `
  tests\test_staff_retirement_workflow.py `
  tests\test_staff_retirement_routes.py `
  tests\test_staff_retirement_consumer_guards.py `
  tests\test_staff_retirement_disposable_mysql_e2e.py `
  tests\test_react_phase3b_public_contracts.py

Set-Location ui_react
npx vitest run src/tests/staff_directory_client.test.ts src/tests/staff_directory_adapter.test.ts `
  src/tests/staff_preferences_client.test.ts src/tests/staff_preferences_adapter.test.ts `
  src/tests/staff_availability_client.test.ts src/tests/staff_lifecycle_client.test.ts `
  src/tests/staff_availability_lifecycle_adapter.test.ts src/tests/staff_page_real_data.test.tsx `
  src/tests/staff_preferences_flow.test.tsx src/tests/staff_availability_flow.test.tsx `
  src/tests/staff_lifecycle_flow.test.tsx src/tests/staff_no_fake_mutation.test.tsx `
  src/tests/staff_request_budget.test.tsx src/tests/staff_control_contract.test.tsx
npm test
npm run lint
npm run build
```

Evidence目錄固定為
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment/`，
至少逐檔產出`contract-field-matrix.md`、`candidate-change-inventory.md`、`verification-receipt.md`、
`browser-smoke-receipt.md`及`open-findings.md`。MySQL必須使用明確`lu_test_*` disposable database，禁止
`union_db`；任何skip使engine/browser gate保持BLOCKED。

## 6. DB gate

本包不變更DB schema／migration／seed／backfill。Current Scope `BLOCKED`（proposed且前置未滿）；
Change inventory `PASS`（0 schema/seed/backfill/destructive）；其餘DB gates `NOT_RUN`。取得exact approval且
前置PASS後Scope才可轉`PASS`。總結`DB_CHANGE_NOT_READY`。
