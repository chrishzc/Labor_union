---
doc_type: work-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation
successors: PROV-20260817-react-admin-orders-query-page-slice; PROV-20260817-react-admin-order-tracker-query-page-slice
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Orders Query / React Integration Owner
domain: Orders Query
supersedes_drift_against: PROV-20260816-react-admin-phase2a-orders-query-real-data
approval_required: 核准此 exact Phase 2A Orders Query Contract Boundary Remediation Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_adoption: ORD-DETAIL-TYPED-QUERY-004; ORD-LIFECYCLE-001
ui_execution_mode: browser-required
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS
---

# Phase 2A Orders Query contract boundary 回歸修復工作包

> 2026-08-17：依逐頁精簡遷移裁決，本提案拆成Orders與Order Tracker兩個單頁工作包；本文件未曾
> 取得exact核准，現標`superseded`，不得再作施工入口。

## 0. Business scenario／現況

操作員開啟 Orders／Order Tracker 時，只能看到可追溯至核准 Pydantic Query view 的資料。現行 React source
重新加入 contract-signing、candidate contact pool、recommend staff、active matching plan、lifecycle-control-state
等 raw／未核准 routes，且 query schemas 再度使用 `.default()`／`z.record()`；這與原 Phase 2A 工作包的
allowlist、strict decoder 與 unavailable 原則衝突。本包只恢復該邊界，不新增功能、不改 backend。

## 1. Exact endpoint allowlist

Client 只可保留以下八個 GET：

1. `/api/v1/orders/summaries`
2. `/api/v1/orders/{case_no}`
3. `/api/v1/orders/{case_no}/calendar-detail`
4. `/api/v1/orders/{case_no}/terms`
5. `/api/v1/orders/{case_no}/form-management-context`
6. `/api/v1/orders/{case_no}/actual-start`
7. `/api/v1/orders/{case_no}/contract-completion`
8. `/api/v1/orders/{case_no}/assignment-plan`

Contract Signing、candidate pool、recommend-staff、active-matching-plan、lifecycle-control-state及其他 raw dict
route 一律移除。Presentation slot 保留並顯示 stable unavailable reason；不得隱藏 Drawer、複製 mock、推導
7-stage／SOP／正式推薦／結清或把 assignment segments 冒充正式推薦。

## 2. Exact write set

- `ui_react/src/api/orders/order_query_schemas.ts`
- `ui_react/src/api/orders/order_query_errors.ts`
- `ui_react/src/api/orders/order_query_client.ts`
- `ui_react/src/adapters/orders/order_summary_adapter.ts`
- `ui_react/src/adapters/orders/order_detail_adapter.ts`
- `ui_react/src/adapters/orders/order_tracker_adapter.ts`
- `ui_react/src/pages/OrdersPage.tsx`
- `ui_react/src/pages/OrderTrackerPage.tsx`
- `ui_react/src/tests/orders_query_client.test.ts`
- `ui_react/src/tests/orders_adapter.test.ts`
- `ui_react/src/tests/orders_page_real_data.test.tsx`
- `ui_react/src/tests/order_tracker_real_data.test.tsx`
- `ui_react/src/tests/orders_no_fake_mutation.test.ts`
- `ui_react/src/tests/fixtures/orders_real_data_fixtures.ts`
- `ui_react/src/tests/challenger_g2_orders_client.test.ts`
- `ui_react/src/tests/challenger_g2_orders_client_resilience.test.ts`
- `ui_react/src/tests/challenger_g5_adversarial_suite.test.tsx`

Integration Owner另可更新本工作包、`02/README.md`、Phase3～6 dependency matrix、Phase5 Orders prerequisite
及專屬 evidence。Phase 2B mutation client/store/adapter/tests、backend、shared transport/Auth、CSS、DB/schema、
其他頁面均禁止修改；頁面修復不得破壞已核准的 Service Dates／Controlled Reopen state machines。

專屬evidence固定落在
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation/`，
至少包含`contract-field-matrix.md`、`candidate-change-inventory.md`、`verification-receipt.md`、
`browser-smoke-receipt.md`與`open-findings.md`；writer不得自行改寫既有Scenario作為唯一oracle。

## 3. Strict contract與防偷懶條款

- Server required field在Zod必須required；nullable不等於optional。禁止 `.default()`、`.catch()`、
  `.passthrough()`、`z.any()`、`z.unknown()`、`z.record()`、unsafe cast與吞掉 drift 的 transform。
- 每個DTO與nested DTO使用strict object decoder；不得依賴Zod strip unknown keys。`order_query_errors.ts`
  同樣禁止`Record<string, any>`／unsafe cast吞掉error drift。
- 每個核准 response model逐欄對齊 Pydantic；calendar-detail只可顯示實際提供的 `service_mode`，不得自造日期。
- 所有 unsupported slots 必須仍可見、可開啟且非 hidden/zero-size；mutation控制維持原生 disabled，Phase 2B
  exact enabled allowlist除外。
- production dependency closure不得引用 `mockData.ts`；fixture不可成為唯一 contract source。
- 頁面只可呼叫allowlist GET與既有Phase2B核准mutation；任何其他 request立即使驗收失敗。
- Orders client每次request當下取得`sessionClient.getToken()`；不得在module load快取token。測試要證明token切換與
  logout後不會沿用舊Bearer；明確test override只能取代該次request。
- 現有 Contract Signing Drawer只顯示 typed terms/contract-completion及明確 unavailable；不得呼叫 raw
  contract-signing GET。正式 successor由獨立 gap裁決。

Request budget固定如下：初始列表只可一次summaries；Tracker在無typed stage projection時不得額外查詢或把
案件猜進七個stage。Matching Drawer最多selected detail＋assignment-plan各一次；Contract Drawer最多detail＋
terms＋contract-completion各一次；Date Drawer最多detail＋calendar-detail＋actual-start各一次，再加既有Phase2B
service-date flow；Cancellation Drawer只可detail一次。單一slot失敗只讓該slot顯示typed unavailable，不得以
`Promise.allSettled`的`null`轉成false／0／pending業務事實。

## 4. G0～G7

- G0：exact approval、dirty baseline、shared-page collision盤點；本包未核准前不得改 production。
- G1：逐欄 matrix凍結，列endpoint／JSON path／Pydantic source／display class／nullable／unavailable原因。
- G2：client negative tests涵蓋missing、wrong type、extra nested、null violation、401/403/timeout/abort。
- G3：adapter不得推導stage、SOP、buffer、settlement、formal recommendation或notification。
- G4：Orders/Tracker所有既有 surface／Drawer／Tab仍存在；Phase2B兩流程focused regression全綠。
- G5：static scan證明八GET allowlist、0 raw clients、0 permissive Zod、0 mock/fake handler。
- G6：full React test/lint/build、strict UTF-8、scoped `git diff --check`。
- G7：真browser以現有兩段式TOTP登入，Network只見核准GET/Phase2B flows；unsupported區塊顯示unavailable。

G1必須採用`ORD-DETAIL-TYPED-QUERY-004`並以`ORD-LIFECYCLE-001`作禁止前端推導的對照；每個READY
欄位至少有一組會改變DOM的sentinel response，不能用全部empty／unavailable通過。測試禁止`.skip`、`.todo`、
`.only`、snapshot-only、`expect(true)`及未被攔截的真網路請求。

三個`challenger_g2_*`／`challenger_g5_*`測試目前直接引用未核准schema／method，必須在本包內改成驗證八個
GET allowlist、strict decode、fresh token、request budget與unsupported unavailable；不得刪檔、skip或保留
18-method surface只為讓舊測試通過。Phase2B source與tests不在write set，僅作fresh regression。

任何 G1～G6 未跑不得因 browser/test data 阻擋而提前結案；最高狀態在 G7 前為
`implemented-awaiting-browser-evidence`。

## 5. Required commands

```powershell
cd ui_react
npx vitest run src/tests/orders_query_client.test.ts src/tests/challenger_g2_orders_client.test.ts `
  src/tests/challenger_g2_orders_client_resilience.test.ts src/tests/orders_adapter.test.ts `
  src/tests/orders_page_real_data.test.tsx src/tests/order_tracker_real_data.test.tsx `
  src/tests/orders_no_fake_mutation.test.ts src/tests/challenger_g5_adversarial_suite.test.tsx
npx vitest run src/tests/orders_service_dates_flow.test.tsx src/tests/orders_reopen_flow.test.tsx `
  src/tests/orders_mutation_client.test.ts src/tests/orders_mutation_adapter.test.ts `
  src/tests/orders_mutation_flow_store.test.ts
npm test
npm run lint
npm run build
cd ..
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase2a-orders-remediation `
  tests/test_order_summary_api_client.py tests/test_order_detail_query.py `
  tests/test_order_calendar_detail_api_client.py tests/test_order_terms_api_client.py `
  tests/test_form_management_query.py tests/test_order_actual_start_api_client.py `
  tests/test_contract_completion_workflow.py tests/test_assignment_plan_workflow.py -q
```

## 6. DB gate

| Gate | 狀態 | 證據／理由 |
|---|---|---|
| Scope gate | PASS | React Query boundary remediation；明確0 DB |
| Change inventory | PASS | schema-only／seed／backfill／destructive皆無 |
| Static release gate | NOT_RUN | 不適用，無DB write set |
| Descriptor gate | NOT_RUN | 不適用 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不適用 |

總結：`DB_CHANGE_NOT_READY`；本包不得引入任何DB變更。
