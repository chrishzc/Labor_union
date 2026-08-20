---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260817-react-admin-order-tracker-query-page-slice
date: 2026-08-17
owner: Order Tracker / React Integration Owner
domain: Orders Query
subsystem: react-admin-order-tracker-page-slice
initiative: react-admin-migration
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
prerequisites: PROV-20260817-react-admin-orders-query-page-slice must be completed at query-real-data-validated; its eight-GET client and strict schemas are read-only inputs
canonical_missing_lineage_owner: PROV-20260817-react-admin-phase3e-order-operational-timeline-gap
approval_required: 核准此 exact React Order Tracker Query Page-Slice Work Package
ui_execution_mode: browser-required
completion_ceiling: query-real-data-validated
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-order-tracker-query-page-slice/
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: tracker page, adapter, tests or completed Orders Query client drift requires fresh read and re-freeze
db_change: none
updated: 2026-08-17
---

# React Order Tracker Query Page-Slice 工作包

> Activation：使用者已明確回覆「核准此 exact React Order Tracker Query Page-Slice Work Package」。

## 0. 目的、前置與完成上限

本包依「逐頁精簡遷移模式」只處理 React `#order-tracker`。它承接完成後的 Orders Query
page-slice，重用既有八項 GET client／strict schemas，不建立第二個 tracker client、不修改
`OrdersPage`，也不新增後端 API。

目前 Tracker live source 仍有四類禁止行為：

1. 透過 compatibility mapper 將 `order_status` 猜成七階段。
2. 依 stage index 生成 11 步 SOP 的 completed／in-progress／pending、固定 notes 與假 timestamp。
3. 生成固定日期、固定文字與假成功狀態的 LINE notification history。
4. 由 stage／摘要欄位推導 waiting、blocker、定金、服務完成、客戶款項與月嫂薪資結清。

本包移除上述 runtime 依賴與假資料，同時保留七階段 navigator／section、訂單卡、Drawer、11 步 SOP
與 LINE tab 的視覺槽位。沒有 server lineage 的槽位必須顯示 `unavailable`，不得以 0、empty success、
pending 或「目前無案件」偽裝已知事實。

前置條件固定為：

```text
PROV-20260817-react-admin-orders-query-page-slice
declared_status = completed
completion = query-real-data-validated
```

若 Orders Query 仍是 `in-progress`／awaiting browser，本包可以完成文件與 source audit，但 production
施工不得開始。Integration Owner 必須在開工當下重新確認八 GET client methods、strict schemas、
final evidence 與 browser/query status。

本包完成上限為 `query-real-data-validated`；不代表 7-stage／SOP／LINE server read model 已完成、
mutation 已啟用、Orders entry 已 cutover 或 Streamlit 已退役。

## 1. Business scenario and authoritative facts

已完成帳密 Challenge → TOTP 的內部操作員開啟 `#order-tracker`：

- 頁面以完成後的 `ordersQueryClient.getOrderSummaries()` 載入一頁去敏 typed summaries。
- Summary cards 只顯示 `OrderSummaryItem` 可證明的 case number、client name、raw order status、staff name、
  dates、service days 與 payable amount；raw `order_status` 明確標示為原始欄位，不是七階段。
- 因目前沒有 typed operational timeline，七階段 section 的案件數固定顯示 `—`，每欄顯示
  「後端尚未提供 typed stage projection」，不可把 loaded orders 分配進任何一欄。
- 已載入摘要另置於「待後端階段投影」區；這是 loaded-scope summary list，不是第八階段，也不修改
  Domain state。
- 打開某訂單 Drawer 只使用已載入 summary，零額外 request。11 個 SOP 名稱可保留為 presentation
  constants，但每一列 status／timestamp／notes 都顯示 unavailable。
- LINE tab 只顯示 case-scoped timeline contract unavailable；不得生成任何 notification row、delivery
  status、recipient、payload、timestamp 或 provider error。

權威來源：

- `OrderSummaryItemSchema`／後端 `OrderSummaryItemView`：卡片可顯示的 server facts。
- `PROV-20260817-react-admin-orders-query-page-slice`：八 GET allowlist、strict decoder、memory bearer、
  request/error behavior。
- `PROV-20260817-react-admin-phase3e-order-operational-timeline-gap`：7-stage／11-step／LINE timeline
  缺 server lineage 的 canonical owner。本包不複製新欄位 gap。
- 使用者已確認的結清裁決：服務完成、客戶款項結清、月嫂薪資核銷是三個獨立 owner projections，
  不得互相推導。

## 2. Query contract and request budget

### 2.1 Reused bounded client

本包只重用：

```text
ordersQueryClient.getOrderSummaries()
→ GET /api/v1/orders/summaries
→ BaseResponse[OrderSummaryPageView]
```

八 GET client其餘七個 methods保持可供其他 Orders surfaces 使用，但 Tracker 第一版不預抓、不逐卡
fan-out，也不為填滿空槽呼叫。不得新增 tracker-specific client、raw fetch、LINE client、lifecycle client、
contract-signing client、candidate pool 或 mutation client。

### 2.2 Request budget

| Operation | Maximum | Rule |
|---|---:|---|
| Initial `#order-tracker` render | 1 summaries GET | StrictMode不得 duplicate；每次 request即時讀 memory bearer |
| Explicit retry | 1 summaries GET per click | Abort/discard previous generation；無 auto retry／polling |
| Open/close order Drawer | 0 GET | 使用 loaded summary only |
| Switch SOP／LINE tabs | 0 GET | unavailable presentation only |
| Click seven stage navigator | 0 GET | scroll to preserved slot only |
| Search/filter/presentation scroll | 0 GET | 若保留，只作用於 loaded summaries |
| Manual LINE replay／any mutation | 0 request | native disabled；無 POST／PUT／PATCH／DELETE |

Client error、401／403、timeout、abort、network、schema mismatch不得轉為空看板或「七欄皆 0」。Error
UI顯示 typed failure並提供 explicit retry；request generation 變更後丟棄 stale response。

## 3. Adapter contract and prohibited derivations

### 3.1 Seven visual slots only

`PIPELINE_COLUMNS` 可保留名稱、順序、說明與色彩作 presentation constants；它不再擁有
`WorkflowStage` business mapping。Adapter output必須改為：

- 七個 `stageSlots`，每個 slot有 stable presentation id、title、description與 `availability: unavailable`。
- `count: null`／UI render `—`；禁止 `0`、`items.length` 或 local stage count。
- `orders: []` 不得被 UI翻譯成「目前無案件停留於此階段」；必須顯示 typed projection unavailable。
- loaded summaries放在獨立 `unclassifiedOrders`／`待後端階段投影`區，不參與 stage allocation。

`order_tracker_adapter.ts` 必須完全移除 `mapOrderStatusToWorkflowStage` import/call及任何等效 switch、map、
regex或default-stage fallback。`order_summary_adapter.ts` 是 Orders Query predecessor-owned read-only input；
本包不競寫。若 compatibility export在 predecessor source仍存在，Tracker dependency closure必須為0引用，
其實體刪除由 Orders Query owner的final cleanup處理，不得為此擴張本包。

### 3.2 Summary card mapping

只允許逐欄映射 server summary：

| Card slot | Source／disposition |
|---|---|
| case identity | `case_no` |
| client | `client_name` |
| raw status | `order_status`，標示「原始訂單狀態（非七階段）」 |
| assigned staff | `staff_name` nullable；null顯示 `—`，不翻譯成 matching conclusion |
| planned/actual dates | server `start_date/end_date/actual_start_date/actual_end_date`；不做日期運算 |
| service days | server `service_days` nullable；null顯示 unavailable |
| amount | server `total_employer_self_pay_payable` nullable；不代表 settled／paid |
| phone/address | unavailable；不得用固定文字冒充 server value |
| waiting/blocker | unavailable；不得從 status、missing string或stage生成 |
| deposit/settlement | unavailable；不得填0或合併三 owner states |

### 3.3 SOP and notification slots

11步名稱保留為固定 UI label；每步 view model只可包含：

```text
stepNo
name
availability = unavailable
status = null
timestamp = null
notes = 後端尚未提供此步驟的 typed root-fact lineage
```

禁止 `completed`／`in_progress`／`pending`，因為 `pending` 也會誤導為已知狀態。禁止依 actual start、staff、
contract signing或stage添加 notes。

Notification tab固定是一個 unavailable sentinel，不是空 success list。移除 `generateNotificationsHistory`
及所有 `NTF-*`、固定 `2026-*` timestamp、成功／失敗 badge、message body與case/client interpolated內容。

### 3.4 Three independent settlement slots

Drawer保留三個獨立顯示位置：

- `order-tracker.settlement.service-completion`
- `order-tracker.settlement.client-finance`
- `order-tracker.settlement.staff-payroll`

本包均顯示 owner-specific typed projection unavailable；不得從 `order_status`、contract completion、deposit、
amount、stage或另一 owner推導。這三個 slot不新增 request。

## 4. Stable UI identities

- `order-tracker.page`
- `order-tracker.query.loading`
- `order-tracker.query.error`
- `order-tracker.query.retry`
- `order-tracker.query.empty`
- `order-tracker.stage-nav.<stage-slot-id>`
- `order-tracker.stage-slot.<stage-slot-id>`
- `order-tracker.stage-count.<stage-slot-id>`（顯示 `—`）
- `order-tracker.stage-unavailable.<stage-slot-id>`
- `order-tracker.unclassified-orders`
- `order-tracker.card.<encoded-case-no>`
- `order-tracker.drawer`
- `order-tracker.drawer.close`
- `order-tracker.drawer.tab.sop`
- `order-tracker.drawer.tab.notifications`
- `order-tracker.sop.step.1` ～ `order-tracker.sop.step.11`
- `order-tracker.sop.unavailable`
- `order-tracker.notifications.unavailable`
- `order-tracker.notifications.replay`（native disabled）
- 三個 `order-tracker.settlement.*` slots

Case number含非CSS安全字元時，stable DOM identity使用既有安全 encoding/helper；不得修改case identity或以
array index／random／timestamp取代。

## 5. Exact write set and ownership

### 5.1 Authorized paths after exact approval and prerequisite completion

Production：

- `ui_react/src/adapters/orders/order_tracker_adapter.ts`
- `ui_react/src/pages/OrderTrackerPage.tsx`
- `ui_react/src/pages/OrderTrackerPage.css`

Tests：

- `ui_react/src/tests/order_tracker_real_data.test.tsx`
- `ui_react/src/tests/order_tracker_adapter.test.ts`（new，如需要）
- `ui_react/src/tests/order_tracker_no_fake_state.test.tsx`（new，如需要）
- `ui_react/src/tests/order_tracker_request_budget.test.tsx`（new，如需要）

Evidence：

- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-order-tracker-query-page-slice/`

Governance：

- 本 Work Package；shared `02/README`、主計畫與dependency matrix由Integration Owner另行同步，
  不在writer write set。

### 5.2 Read-only inputs

- `ui_react/src/api/orders/order_query_client.ts`
- `ui_react/src/api/orders/order_query_schemas.ts`
- `ui_react/src/api/orders/order_query_errors.ts`
- `ui_react/src/adapters/orders/order_summary_adapter.ts`
- Orders Query fixtures/tests/evidence
- `OrdersPage.tsx/.css`與所有Phase 2B mutation files

### 5.3 Forbidden writes／operations

- 不修改 `OrdersPage.tsx/.css`、Orders eight-GET client/schemas/errors、summary/detail adapters、shared
  transport/runtime decoder、Auth、App、Drawer、MasterLayout、package/lock/config或其他頁面。
- 不修改backend、Domain、repository、DB/schema/seed/migration/backfill、Streamlit、entry registry、
  Phase5/6 cutover或retirement files。
- 不建立 stage／SOP／LINE public contract、timeline owner或新gap；沿用Phase3E canonical gap。
- 不啟用LINE replay、auto-completion、form action、matching、contract、settlement或其他mutation。
- 不對`union_db`執行mutation、seed、repair、migration或建立資料；existing DB只供browser GET observation。
- 不commit、stage、push、reset、clean、stash、checkout或建立worktree。

## 6. Focused tests and anti-fake gates

### G0 Scope／prerequisite

- Orders Query predecessor已`completed/query-real-data-validated`，八 GET client current source與evidence fresh-read。
- Tracker exact approval、dirty baseline與三個production paths唯一writer已記錄。
- 0 OrdersPage／client／shared／backend／DB diff。

### G1 Adapter no-derivation

- Static/focused tests證明Tracker dependency closure沒有 `mapOrderStatusToWorkflowStage`、stage switch／fallback、
  `generateSopChecklist`、`generateNotificationsHistory`、`NTF-`、fixed timestamp、waiting text或settlement inference。
- 两筆相同summary但不同`order_status`，只會改raw-status label，不會改stage slot、SOP或notification DOM。
- 七個stage count全部是unavailable／`—`，不會變成0或items count。

### G2 Page request/state behavior

- Initial success、empty、typed error、401/403、timeout、abort、retry與stale response discard。
- 初次render最多1 summaries GET；Drawer／tabs／stage nav／disabled replay皆0 request。
- React StrictMode不得duplicate GET；retry每次明確點擊最多1 GET。
- Empty summaries顯示「目前loaded scope沒有訂單摘要」，七欄仍是projection unavailable；不能顯示
  「七階段均無案件」。

### G3 UI preservation

- 七階nav與七section、loaded summary cards、wide Drawer、雙tab、11個step slots、LINE slot與三個結清
  slots均存在且stable IDs可查。
- Summary DOM逐欄對應server facts；nullable/unopened欄位顯示unavailable／`—`。
- 11步 status/timestamp/notes不顯示假progress；LINE tab不顯示假record；manual replay native disabled。

### G4 Anti-fake／static

- 0 `mockData`、fixed case/client/staff facts、`Date.now/Math.random` identity、hardcoded business timestamp、
  `alert/confirm/prompt`、localStorage/sessionStorage、non-GET、fake success。
- 禁止`.skip/.todo/.only`、snapshot-only、zero assertion與unexpected live network。
- Focused Vitest、Orders Query regression、`npm run lint`、`npm run build`、strict UTF-8、file header、
  secret/PII scan、scoped `git diff --check`與write-set audit通過。

## 7. Real browser GET acceptance

取得exact approval且Orders Query前置完成後，以真實FastAPI + Vite、真帳密→TOTP memory session執行：

1. 打開`http://127.0.0.1:5173/#order-tracker`，Network最多一個
   `GET /api/v1/orders/summaries`；不得POST／PUT／PATCH／DELETE。
2. 將至少一筆去敏response的`case_no/client_name/order_status/dates/service_days/amount/staff_name`
   與「待後端階段投影」card DOM逐欄比對；`order_status`只顯示raw label。
3. 確認七個stage nav/sections存在，count皆`—`，每欄顯示typed stage projection unavailable；不得有
   order card被分入stage，也不得顯示「0筆」或「目前無案件」。
4. 開啟card Drawer：0額外GET；11步名稱存在且每一步status/timestamp/lineage unavailable。
5. 切換LINE tab：0額外GET、無fake record，case-scoped timeline unavailable，manual replay disabled。
6. 三個settlement slot分開且unavailable；不得合併成一個「已結清」。
7. 驗證empty、explicit retry、reload、auth expiry及stale request；沒有memory token時不得anonymous fetch。

Browser unavailable時receipt標`BLOCKED_REAL_BROWSER_EVIDENCE`，不得以Happy DOM、fixture、HTTP 200、舊
Orders receipt或Streamlit screenshot代替。

## 8. Required evidence

執行時在專屬evidence directory產出：

- `order-tracker-evidence-matrix-draft.md`（本次docs/scout輸入；不是freeze receipt）
- `candidate-change-inventory.md`
- `contract-matrix.md`
- `verification-receipt.md`
- `browser-smoke-receipt.md`
- `open-findings.md`

所有pass counts必須來自final edit後fresh-run；Orders Query前置、browser與Tracker自身gate分開列，不得用
前置通過冒充Tracker完成。

## 9. DB gate（0 DB change）

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | BLOCKED | proposed package等待exact approval，且Orders Query前置目前仍須確認completed |
| Change inventory | PASS | schema-only、system-seed、business-row-backfill、destructive均為0 |
| Static release gate | NOT_RUN | 無schema/release變更 |
| Descriptor gate | NOT_RUN | 無owned-object變更 |
| Read-only plan gate | NOT_RUN | 不執行DB migration plan |
| Engine verification gate | NOT_RUN | query-only page slice不建立DB、不以UI冒充engine evidence |
| Developer acceptance gate | NOT_RUN | existing DB只供GET browser observation |

結論固定為`DB_CHANGE_NOT_READY`；這不阻擋前置完成後的Tracker query-only施工，但不授權mutation／DB。

## 10. Rollback and successor routing

- Tracker query故障時保留既有Streamlit Orders entry作presentation fallback；不回滾Domain data。
- 7-stage／11-step／LINE timeline的server-ownedread model沿用Phase3E gap，完成前slots維持unavailable。
- Orders Query、Tracker與Phase2B mutation evidence分開；任何一者通過不自動解鎖entry cutover／retirement。
- 本包不修改或建立Phase5／6文件；由Integration Owner在Tracker完成後以最新entry evidence另行裁決。
