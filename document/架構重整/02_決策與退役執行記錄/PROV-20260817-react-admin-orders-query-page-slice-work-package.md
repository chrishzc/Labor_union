---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260817-react-admin-orders-query-page-slice
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: relevant paths must be freshly read and re-frozen at execution start
owner: Orders Query / React Integration Owner
domain: Orders Query
subsystem: react-admin-orders-page-slice
initiative: react-admin-migration
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_adoption: ORD-DETAIL-TYPED-QUERY-004; ORD-LIFECYCLE-001
ui_execution_mode: browser-required
partially_supersedes: PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation-work-package (OrdersPage scope only)
approval_required: 核准此 exact React Orders Query Page-Slice Work Package
db_change: none
updated: 2026-08-17
---

# React Orders Query Page-Slice 工作包

> Activation：使用者已明確回覆「核准此 exact React Orders Query Page-Slice Work Package」。

## 0. 目的與承接關係

本包只把`#orders`的React real-data query接線收斂成一個最小page slice，承接舊remediation的
OrdersPage範圍；`#order-tracker`必須另立自己的page-slice，不得競寫本包。
本包只處理 query client allowlist、strict response decoder、既有 UI slot 的 unavailable 顯示，以及移除
前端對正式業務狀態的猜測；不新增後端能力，不改資料庫，不重做 Domain／Scenario，也不把 query 完成
宣稱為 mutation、entry cutover 或 Streamlit 退役。

目前 source fresh-read 已確認的主要漂移：

- `order_query_client.ts` 仍暴露未核准的 candidate pool、recommend staff、active matching plan、matching
  contact state、lifecycle control state、contract-signing 及其他非八項 allowlist 方法。
- `order_query_schemas.ts` 仍有 `.default()`、`z.record()` 等會吞掉 response drift 的 permissive 形狀。
- `order_summary_adapter.ts` 依 `order_status` 推導七階段與 settlement／waiting 文案。
- `order_detail_adapter.ts` 自算七天 buffer、正式推薦／意願等業務結果。

上述項目是本包的施工對象，不得以目前測試綠燈、mock fixture 或既有頁面能渲染作為已完成證據。

## 1. 業務場景與不變量

操作員開啟 `#orders` 時：

1. 列表與 Drawer 只顯示可追溯到後端 typed Query view 的資料。
2. 服務完成、客戶款項結清、月嫂薪資核銷與正式推薦各自沒有
   server projection 時，原本的 UI slot 必須保留並明確顯示 unavailable；不得由 `order_status`、日期、
   stage index 或另一個 Domain 的欄位推導。
3. Service Dates Confirm 與 Controlled Reopen 是已核准的 Phase 2B mutation；本包不得修改其
   client、store、adapter、state machine、request header、receipt 或 re-query 行為。
4. 所有 query request 每次發送當下取得 volatile session token；不得快取 token、寫入 localStorage、
   sessionStorage、cookie、URL 或 fixture。
5. 本包不碰 `union_db`，不建立 disposable DB，不執行 seed／migration／repair／mutation。

## 2. Query allowlist 與禁止面

`order_query_client.ts` 最終只保留以下八個 Orders Query GET；路徑、方法名稱與 response decoder 必須
一一對應，不能以 alias 保留被禁止方法：

| Stable ID | HTTP endpoint | 使用 surface |
|---|---|---|
| `ORD-QRY-001` | `GET /api/v1/orders/summaries` | Orders 列表 |
| `ORD-QRY-002` | `GET /api/v1/orders/{case_no}` | Orders detail 投影 |
| `ORD-QRY-003` | `GET /api/v1/orders/{case_no}/calendar-detail` | 日期 Drawer 可提供欄位 |
| `ORD-QRY-004` | `GET /api/v1/orders/{case_no}/terms` | 條款 Drawer |
| `ORD-QRY-005` | `GET /api/v1/orders/{case_no}/form-management-context` | 表單管理 typed context |
| `ORD-QRY-006` | `GET /api/v1/orders/{case_no}/actual-start` | 日期／開工查詢投影 |
| `ORD-QRY-007` | `GET /api/v1/orders/{case_no}/contract-completion` | 合約完工查詢投影 |
| `ORD-QRY-008` | `GET /api/v1/orders/{case_no}/assignment-plan` | 正式排班／assignment-owned projection |

以下方法與 endpoint 必須從 query client、page call site、fixture contract 與 tests 移除；不能改名、
包裝或以 `Promise.allSettled` 隱藏：

- `getCandidateContactPool` / `/candidate-contact-pool`
- `recommendStaff` / `/api/v1/matches/recommend-staff`
- `getActiveMatchingPlan` / `/matching-plans/active`
- `getMatchingPlanContactState` / `/contact-state`
- `getLifecycleControlState` / `/lifecycle-control-state`
- `getContractSigning` / `/contract-signing`
- query client 內不屬於上述八項的 cancellation、service-dates、schedule-confirmation、statistics
  或其他未列入本包的 GET；若既有 Drawer 需要該資料，slot 保留但顯示 stable unavailable。

Service Dates 的 query／preview／apply／receipt／re-query 僅由既有 Phase 2B mutation client／adapter
擁有；Controlled Reopen 同理。不得為了滿足八項 allowlist 而移動或重構 mutation 檔案。

## 3. Strict schema 與 adapter disposition

### 3.1 Schema

`ui_react/src/api/orders/order_query_schemas.ts` 必須逐欄對齊對應 Pydantic Query view：

- required 欄位在 Zod 中 required；server nullable 使用 `.nullable()`；optional 與 nullable 不可混用。
- 全部 object 使用 `.strict()`。
- 禁止 `.default()`、`.catch()`、`.passthrough()`、`z.any()`、`z.unknown()`、`z.record()`、
  unsafe cast、吞錯 transform 及以 `Record<string, any>` 表示錯誤 payload。
- missing required、wrong primitive、extra key、null violation、錯誤 envelope 必須轉為 typed client
  decode error，不能渲染半成品。
- envelope 欄位不得用 default 補成功、訊息或空陣列；實際缺少即 fail closed。

### 3.2 Page／adapter

| Surface | 保留 | 必須移除或改為 unavailable |
|---|---|---|
| Orders summary | server `order_status`、server 日期／地址／客戶欄位 | `order_status → 7-stage`、deposit／settlement／waiting 推導 |
| Date Drawer | typed detail/calendar/actual-start 與 Phase 2B mutation-owned projection | 前端日期加減、7 天 buffer、假雙邊確認 |
| Matching Drawer | typed assignment-plan 可提供的 assignment-owned projection | candidate pool、recommendation、willingness、正式推薦／媒合狀態故事 |
| Contract Drawer | terms、detail、contract-completion typed fields | contract-signing raw GET、簽回／定金／結清猜測 |
| Cancellation Drawer | 既有 UI slot | 非 allowlist query；原位顯示 unavailable，不能假算退款 |

任何 unsupported slot 都要有可見、非 hidden、非 zero-size 的穩定文案，例如
`後端尚未提供 typed projection`；不能把 `null`、`false`、`0` 或 `pending` 當業務事實。

## 4. Exact write set 與禁止範圍

### 4.1 未來執行本包的 exact write set

- `ui_react/src/api/orders/order_query_schemas.ts`
- `ui_react/src/api/orders/order_query_errors.ts`
- `ui_react/src/api/orders/order_query_client.ts`
- `ui_react/src/adapters/orders/order_summary_adapter.ts`
- `ui_react/src/adapters/orders/order_detail_adapter.ts`
- `ui_react/src/pages/OrdersPage.tsx`
- `ui_react/src/tests/orders_query_client.test.ts`
- `ui_react/src/tests/orders_adapter.test.ts`
- `ui_react/src/tests/orders_page_real_data.test.tsx`
- `ui_react/src/tests/orders_no_fake_mutation.test.ts`
- `ui_react/src/tests/fixtures/orders_real_data_fixtures.ts`
- `ui_react/src/tests/challenger_g2_orders_client.test.ts`
- `ui_react/src/tests/challenger_g2_orders_client_resilience.test.ts`
- `ui_react/src/tests/challenger_g5_adversarial_suite.test.tsx`

本次只建立 Work Package 與 evidence matrix，以上 production／tests 均未被本次文件任務修改。

### 4.2 明確禁止修改

`ui_react/src/api/orders/order_mutation_client.ts`、`order_mutation_schemas.ts`、
`order_mutation_adapter.ts`、`order_mutation_flow_store.ts`、Phase 2B mutation tests、
`transport.ts`、`runtime_decoder.ts`、Auth、`App.tsx`、`MasterLayout`、`OrderTrackerPage.tsx`、
`order_tracker_adapter.ts`、任何 backend／schema／DB／migration、CSS、其他頁面、README、主計畫、
shared catalog、Phase 3～6 dependency matrix 與 Git history。

## 5. Request budget 與 stable control IDs

### 5.1 Request budget

- Initial Orders load：只可一次 `ORD-QRY-001`；refresh 是明確的 user action，不能 background polling。
- Date Drawer：最多各一次 `ORD-QRY-002`、`ORD-QRY-003`、`ORD-QRY-006`；Phase 2B 自己的
  Service Dates query／preview／apply／re-query 不計入 query client，但仍須遵守其既有 flow budget。
- Matching Drawer：最多各一次 `ORD-QRY-002`、`ORD-QRY-008`；其餘 matching endpoint 不得送出。
- Contract Drawer：最多各一次 `ORD-QRY-002`、`ORD-QRY-004`、`ORD-QRY-007`；contract-signing slot unavailable。
- Form context：只有實際 UI surface 需要時才送出一次 `ORD-QRY-005`；不可為測試或預抓而呼叫。
- Unsupported／unavailable slot：零 request。每個 endpoint failure 只影響該 slot，不得由 `allSettled(null)`
  生成業務狀態。

### 5.2 Stable IDs（驗收與 DOM）

- `ORD-QRY-001`～`ORD-QRY-008`：GET allowlist。
- `ORD-SLOT-UNAVAILABLE-001`：unsupported slot 可見 unavailable sentinel。
- `ORD-NO-DERIVATION-001`：不得由 status／日期／stage 產生正式狀態。
- `ORD-REQUEST-BUDGET-001`：初始／Drawer request 次數上限。
- `ORD-MUTATION-PRESERVE-001`：Phase 2B mutation source regression sentinel。
- 既有 `data-control-id` 必須保持相容；本包不得重新命名或解鎖 Phase 2B controls。

## 6. 驗收 Gates

- **G0 Scope**：所有實作 diff 只在 §4.1，0 backend／0 DB；Phase 2B 檔案無 diff。
- **G1 Contract matrix**：使用 evidence matrix draft 凍結八項 endpoint、Pydantic view、Zod schema、UI surface、
  unavailable disposition；不得用 fixture 取代 live schema。
- **G2 Strict decoder**：負向測試涵蓋 required／nullable／extra／wrong primitive／error envelope。
- **G3 No derivation**：靜態與focused tests證明OrdersPage沒有stage／settlement／buffer／recommendation
  generation；沒有固定日期或fake success。OrderTracker的SOP／LINE generator由其後續page-slice處理。
- **G4 UI preservation**：Orders 四個 Drawer均仍存在；unsupported slot顯示unavailable；Phase 2B
  日期／重開flows focused regression全綠。OrderTracker不在本包驗收範圍。
- **G5 Request budget**：spy／network assertions 證明初始與各 Drawer 不超過 §5.1，禁止被移除 endpoint。
- **G6 Static**：`npm test`、`npm run lint`、`npm run build`、strict UTF-8、scoped `git diff --check`；
  禁止 `.skip`、`.todo`、`.only`、snapshot-only、`expect(true)` 與未攔截真網路測試。
- **G7 Browser**：以真實兩段式 TOTP 登入，在既有 DB 上只觀察 GET query；Network／DOM 對照 matrix，不能執行
  mutation、seed、migration 或資料修復。瀏覽器未驗證前最高狀態為 `implemented-awaiting-browser-evidence`。

## 7. Required evidence

專屬 evidence directory：
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-orders-query-page-slice/`

本包至少產出：

- `evidence-matrix-draft.md`（本次建立；執行時由 Integration Owner 以 fresh source 凍結）
- `candidate-change-inventory.md`
- `contract-matrix.md`
- `verification-receipt.md`
- `browser-smoke-receipt.md`
- `open-findings.md`

Browser receipt 必須保留去敏 Network／DOM 證據、登入方式（TOTP，不記錄帳密／token）、request budget、
unavailable sentinel 與 0 mutation；不能用 happy-dom、HTTP 200 單獨或既有歷史 receipt 代替。

## 8. Commands（由核准後 writer 執行）

```powershell
cd D:\project\Labor_union\ui_react
npx vitest run src/tests/orders_query_client.test.ts src/tests/orders_adapter.test.ts src/tests/orders_page_real_data.test.tsx src/tests/orders_no_fake_mutation.test.ts src/tests/challenger_g2_orders_client.test.ts src/tests/challenger_g2_orders_client_resilience.test.ts src/tests/challenger_g5_adversarial_suite.test.tsx
npx vitest run src/tests/orders_service_dates_flow.test.tsx src/tests/orders_reopen_flow.test.tsx src/tests/orders_mutation_client.test.ts src/tests/orders_mutation_adapter.test.ts src/tests/orders_mutation_flow_store.test.ts
npm test
npm run lint
npm run build
cd D:\project\Labor_union
git diff --check
```

本包不執行 DB command；既有 DB 只在 G7 browser query evidence 使用。

## 9. DB gate（0 DB change）

| Gate | 狀態 | 證據／理由 |
|---|---|---|
| Scope gate | BLOCKED | React Orders query page slice；等待exact approval，0 DB write set |
| Change inventory | PASS | schema-only、system-seed、business-row-backfill、destructive 均為 0 |
| Static release gate | NOT_RUN | 不適用，無 schema／migration artifact |
| Descriptor gate | NOT_RUN | 不適用 |
| Read-only plan gate | NOT_RUN | 不執行 DB migration plan |
| Engine verification gate | NOT_RUN | 不建立 disposable DB；本包不是 DB 變更 |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫；G7 僅做 query-only browser observation |

依專案規範，任一必要 DB gate 為 `NOT_RUN` 時總結固定為 `DB_CHANGE_NOT_READY`；這不阻擋本包的 React
query page-slice 執行，但不得宣稱任何 DB 變更已驗證。

## 10. 完成狀態邊界

本包完成上限為 `query-real-data-validated`（若八項 public contract 與 strict decoder 均通過）或
`implemented-awaiting-browser-evidence`。它不代表：

- Service Dates／Controlled Reopen mutation 改良或重新驗收完成；
- matching、contract signing、cancellation新能力或OrderTracker的SOP／LINE query完成；
- Orders或OrderTracker entry cutover完成；
- Streamlit `ui/pages/02_orders.py` 退役；
- Phase 4～6 的任何 predecessor 已被解鎖。
