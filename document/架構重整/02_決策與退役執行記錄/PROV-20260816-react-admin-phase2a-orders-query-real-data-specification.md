---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase2a-orders-query-real-data-specification
owner: global-admin-web-presentation / orders-query
base_ref: ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922
date: 2026-08-16
revision: V2
approved_by: human-owner
approved_at: 2026-08-16
approval_scope: exact-phase2a-specification-and-work-package
depends_on:
  - PROV-20260816-react-admin-migration-foundation-work-package
  - PROV-20260816-react-admin-phase2a-orders-query-real-data
---

# React 管理端 Phase 2A：Orders／OrderTracker Query Real-data 實作規格（V2）

## 1. 文件狀態與目的

本文件是 `OrdersPage`／`OrderTrackerPage` 第一個 real-data 唯讀切片的 approved 實作規格。
它保存目前已確認的 React UI，不重新設計頁面、Drawer、Tab、7 階段導覽或 11 步 SOP 外觀；實作重點是
把可以由 current typed API 證明的 mock 資料換成 real query，並對缺少正式契約的區塊 fail closed。

本文件不是「整個 Orders 功能已完成」的聲明，也不授權 mutation、backend、schema、Streamlit cutover、
deployment 或外部 LINE 副作用。2026-08-16 已取得人工對此規格與對應 exact Work Package 的明確核准；
production code 仍只能依該工作包的 exact write set、G0–G6 gate 與 fail-closed 邊界施工。

### 1.1 人工核准與補強邊界

- 人工核准記錄：2026-08-16，人工回覆「核准，可以補強」。
- 核准範圍：本文件 V2 與對應 Phase 2A Work Package V3 的既定 Orders／OrderTracker query-only scope。
- 可直接補強：證據精度、negative tests、反作弊掃描、代理 prompt、receipt、錯誤隔離與 fail-closed 驗收。
- 必須重新人工核准：backend／public API、DB／schema、Auth／TOTP／session、任何 mutation、其他頁面、
  UI 資訊架構或版面重設、Streamlit cutover、launcher、deployment、外部 LINE 副作用或既定 write set 擴張。
- `approved` 只代表可以開始依工作包施工，不代表已實作、已驗收、可部署或可退役 Streamlit。

## 2. 人工裁決與不可推翻的不變量

1. 既有 React UI 是本波 presentation baseline；不得刪除、重畫或改用另一套資訊架構來迴避接線困難。
2. 客戶正式推薦預設是一位月嫂。只有 server 證明單一月嫂無法覆蓋全部正式服務日期時，才可把
   2–4 位月嫂的不重疊連續分段作為一個整體正式推薦；shortlist 不等於正式推薦。
3. `服務完成`、`客戶款項結清`、`月嫂薪資核銷` 是三個獨立 owner projection，不得合成一個
   settlement／completed 狀態，也不得由 React 互相推導。
4. 緊急聯絡電話缺漏是 warning-only；只顯示警告並允許繼續媒合，不得成為 disabled predicate。
5. React 不解析中文狀態字串、金額、日期、候選人陣列或 error message 來重建 Domain state machine。
6. 11 個 SOP 名稱可作 presentation constant；每列 status、timestamp、notes 必須來自 typed server view。
   沒有正式 view 時顯示「資料尚未提供」，不得沿用 mock 的 pending／in-progress／completed。

## 3. 實際 UI 範圍

本波盤點與保留的 visible surface 如下；「保留」不代表其 mutation 已獲授權。

| Surface | 既有結構 | Phase 2A 處置 |
|---|---|---|
| Orders header／filters／cards | 新建訂單、8 filters、訂單卡、條款／媒合／日期／取消／重開入口 | 卡片查詢接 real data；缺欄顯示 unavailable；所有 mutation 保留位置但 disabled |
| 日期確認 Drawer | 日期、假日、精算 snapshot、雙方確認、轉正式履約 | 只顯示可證明的 query facts；不得前端算日期或推 gate |
| 媒合 Drawer | 候選池、Info-1/2、意願、履歷、客戶決策、waiting lock | 本波不接 mutation；不得使用 `MOCK_STAFF` 或 local state 冒充正式結果 |
| 條款／簽署 Drawer | 條款、月嫂簽署、訂金、客戶簽署 | 條款 query 可接；其他僅在 contract freeze 後接 read view |
| 取消／退款 Drawer | 金額拆分與 Apply | 移除前端公式；本波顯示 unavailable，Apply disabled |
| OrderTracker | sticky 7-stage navigator、stage sections、cards | 沒有 typed stage projection 時不得以 `order_status` 猜階段 |
| Tracker SOP Tab | 11 步 row、status、timestamp、notes | 保留 11 個名稱；動態資料缺 contract 時顯示 unavailable |
| Tracker Notification Tab | order-scoped timeline、failed replay | 保留 Tab；沒有核准的 typed LINE timeline 時顯示 unavailable；manual replay disabled |

## 4. Contract-first field matrix

任何 writer 開工前，Contract Scout 必須在 current HEAD 產出並 freeze 下列逐欄矩陣：

`surface → current UI field → exact endpoint → JSON path → server schema／source → disposition`

Disposition 只能使用：

- `READY_TYPED`：route 有明確 Pydantic response model，React 使用 strict Zod decoder。
- `CLIENT_DECODER_REQUIRED`：route 尚為 raw response，但有可凍結、可測的 bounded server view；須建立獨立
  bounded client，不得只驗證 envelope；Phase 2A current exact endpoints不含此類例外，任何raw route預設out of scope。
- `PRESENTATION_CONSTANT`：純 UI 名稱／順序，不含業務 status、金額、日期或成功結果。
- `BACKEND_GAP`：沒有足以支持該欄位的正式 read contract；本波顯示 unavailable。
- `OUT_OF_SCOPE_MUTATION`：本波不可執行，控制項保留但 disabled。

矩陣沒有 freeze 前，API Client、Adapter 與 Page Writer 不得自行挑 route、複製 mock、增加 N+1 query
或把 raw payload 穿透 component。

## 5. Current contract baseline

### 5.1 可直接使用的 typed query

| Endpoint | Typed view | 本波可證明的資料 |
|---|---|---|
| `GET /api/v1/orders/summaries` | `OrderSummaryPageView` | case、client、server order status、staff、identity、日期、service days、self-pay、cursor、ETag |
| `GET /api/v1/orders/{case_no}` | `OrderDetailView` | selected-case detail 中已宣告的 ids、日期、服務時數、floor fee、deposit date、contract identity |
| `GET /api/v1/orders/{case_no}/calendar-detail` | `OrderCalendarDetailView` | `service_mode`；不得把它擴張成完整 calendar／date-confirmation state |
| `GET /api/v1/orders/{case_no}/terms` | `OrderTermsQueryView` | versioned order terms、服務時間、下廚、floor fee 與 lock flag |
| `GET /api/v1/orders/{case_no}/form-management-context` | `FormManagementCaseContextView` | 只使用該 typed view 明確宣告的表單上下文 |
| `GET /api/v1/orders/{case_no}/actual-start` | `ActualStartQueryView` | actual／planned start、lock 與跨 Domain versions；不是日期確認完整 state |
| `GET /api/v1/orders/{case_no}/contract-completion` | `ContractCompletionQueryView` | contract/deposit readiness、lifecycle status與 domain blockers；不是三結清總覽 |
| `GET /api/v1/orders/{case_no}/assignment-plan` | `AssignmentPlanQueryView` | 1–4 effective assignment segments與 official dates；不等於客戶 formal recommendation |

列表必須 cursor-based；不得呼叫已退役的 `GET /api/v1/orders`。detail、terms、calendar 只在使用者開啟
相應 selected-case surface 時 lazy query，禁止為每張卡做 N+1 detail preload。

### 5.2 已知 contract gaps

下列資料目前不能由現有 typed Orders views完整證明，Phase 2A 不得自行補值：

- 卡片所需的完整電話、地址、合約／訂金金額、match score、waiting lock、blocker／warning split。
- canonical 7-stage tracker projection與每階段 count。
- 11-step SOP 每列的 status、timestamp、notes 與 root-fact lineage。
- order-scoped LINE delivery timeline、retry count、manual replay readiness／receipt。
- `服務完成`、`客戶款項結清`、`月嫂薪資核銷` 三個獨立 typed projections。
- formal recommendation identity，以及單一或 2–4 segment fallback 的整體 recommendation status。
- emergency-contact warning view。

`GET /api/v1/orders/{case_no}/lifecycle-control-state` 目前為 `BaseResponse[dict[str, Any]]`，不可因 route
存在就標 `READY_TYPED`。LINE notification timeline、contract signing 或其他跨 Domain query 必須使用其
各自 bounded client；禁止塞入 `api/orders` client。若其 route／schema仍是 dirty candidate 或 raw dict，
預設 disposition 為 `BACKEND_GAP`，除非人工另行核准 contract exception。

### 5.3 Pre-execution field matrix baseline

本表由 current HEAD `ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922` 的 schema／route直接核對；實作前
Contract Scout仍須對最新 HEAD重驗並由 Integration Owner freeze。

| Existing UI field／surface | Current source | Disposition | 約束 |
|---|---|---|---|
| `id` | summary/detail `case_no` | `READY_TYPED` | 直接顯示，不重新編號 |
| `clientName` | summary/detail `client_name` | `READY_TYPED` | 不從其他 client合併猜值 |
| `serviceDays` | summary/detail/terms | `READY_TYPED` | nullable依原contract呈現 |
| planned／actual dates | summary/detail/actual-start | `READY_TYPED` | 不計算 end／buffer |
| service time／cooking／floor fee | terms | `READY_TYPED` | 只在selected-case lazy query |
| canonical Orders status | summary/detail/contract-completion | `READY_TYPED` | 只能顯示原值，不能映射成7-stage |
| `depositSettled` | contract-completion | `READY_TYPED` | 不是client overall settlement |
| effective assignment segments | assignment-plan | `READY_TYPED` | 是正式execution plan，不等於formal recommendation |
| `clientPhone` | 無 authorized typed view | `BACKEND_GAP` | 不顯示mock或未遮罩資料 |
| full `serviceAddress` | form context只有city | `BACKEND_GAP` | city不可冒充完整地址 |
| `contractAmount` | 無相同語意欄位 | `BACKEND_GAP` | self-pay payable不可改名成契約總額 |
| `depositAmount` | 無order workbench typed amount | `BACKEND_GAP` | deposit date／settled不可推金額 |
| assigned caregiver phone／match score | 無authorized typed view | `BACKEND_GAP` | summary staff name不可冒充完整推薦／正式assignment |
| 7-stage／counts／`waitingFor` | lifecycle route仍raw且無SOP projection | `BACKEND_GAP` | 不解析中文status |
| blocker／warning split | summary/detail未提供 | `BACKEND_GAP` | 不由nullable欄位推導 |
| matching plan／formal recommendation | active matching route raw | `BACKEND_GAP` | candidate pool或assignments不可冒充 |
| date confirmation participants／lineage | 無此Orders typed workbench view | `BACKEND_GAP` | 不用local booleans |
| 11-step status／timestamp／notes | 完全來自mock | `BACKEND_GAP` | 只有11個名稱是`PRESENTATION_CONSTANT` |
| order notification timeline | current candidate route raw／跨LINE | `BACKEND_GAP` | 固定兩筆通知與replay假成功必須移除 |
| client settlement | receipt query無overall projection | `BACKEND_GAP` | 不用every/sum推結清 |
| staff payout settlement | staff-scoped query無case composite | `BACKEND_GAP` | 多segment不可前端聚合 |
| emergency-contact warning | 無owner／typed warning | `BACKEND_GAP` | Phase 2A不得自行造warning或blocker |
| 新建／媒合／日期送出／取消／重開／manual replay | POST／PUT／PATCH／DELETE actions | `OUT_OF_SCOPE_MUTATION` | 原位disabled，零request、零local成功 |

主要 source evidence：`api/schemas/order_summary.py`、`order_detail.py`、`order_calendar_detail.py`、
`order_terms.py`、`order_actual_start.py`、`order_contract_completion.py`、`assignment_plan.py`、
`api/routes/orders.py` 及相應 route files。React 現況證據為 `OrdersPage.tsx`、`OrderTrackerPage.tsx`、
`api/mockData.ts`；這些 live mock只能證明待替換範圍，不能成為 server contract。

### 5.4 必須保留的 live-drift 記錄

- React 現況允許選取多位候選並一次發送競爭履歷；這不符合「一般一位，僅單人無法全期覆蓋才可
  2–4 分段作一個正式推薦」。current assignment-plan接受1–4 segments，但其 Query不證明
  multi-caregiver fallback predicate，也不提供formal-recommendation identity，因此本波不得改名冒充。
- mock 把缺少緊急電話列為媒合 blocker，與人工 warning-only裁決相反；移除mock後不得在React重建該阻擋。
- mock 的 `settlement_payout` 及Tracker最後階段把服務完成、客戶尾款與月嫂薪資合併；本波不得沿用該
  動態狀態語意。7-stage label可保留presentation，但在typed composite projection出現前其count/status unavailable。
- OrdersPage current handlers會本機發送LINE成功、改候選／客戶決策／lock、計算日期與退款；Phase 2A
  必須保留控制位置但清除假成功及business-state mutation，不能以「mutation out of scope」為由原樣留下。

## 6. React data boundary

### 6.1 API client

- 每個成功 payload 使用 `z.strictObject` 或等價 strict schema，驗證 envelope 與完整 `data`。
- 禁止 `as SomeType`、`unknown as`、`.passthrough()`、catch-all 或只驗外層 envelope。
- transport 必須保留Authorization、timeout、AbortSignal與typed errors。Orders client每次method invocation才
  從`sessionClient.getToken()`取得current in-memory token，禁止module-load快取；token切換／logout後不得沿用
  舊token。缺token時以bounded `OrdersSessionRequiredError` fail before request，零network。
- Current shared transport沒有自動request/correlation ID注入；Phase 2A不製造或宣稱該證據。若後續需要
  observable correlation header，必須另行核准shared-transport變更。
- summary client 支援 cursor、body內typed `etag`、query change abort及append dedupe。本波不送
  `If-None-Match`、不處理304，因current shared transport不暴露response status／headers；不得直接fetch
  或建立第二套transport繞過，後續須以`SHARED_TRANSPORT_RESPONSE_METADATA_GAP`另案裁決。
- case number 必須安全 URL encode。
- 現有 shared `createBaseResponseSchema()` 使用一般 `z.object`，會移除而非拒絕未知欄位；本包禁止修改
  shared hot spot，因此 Orders client 必須以 orders-local strict envelope封閉此差距並提供 negative tests。
- Server-required key必須required；nullable不等於optional。禁止以`z.unknown`、`z.record`、`.catch()`、
  `.default()`、`.coerce`、`.preprocess`、`.transform`或寬鬆union吞掉schema drift。只有live Pydantic明確有
  default／optional語意的欄位可以對應，且仍須negative tests。

### 6.2 Adapter

- Adapter 只做 server DTO 到既有 presentation view model 的命名與 nullable mapping。
- Adapter 不推 stage、settlement、coverage、金額、日期、warning severity 或 action readiness。
- `BACKEND_GAP` 使用明確 discriminated unavailable state；不得填空字串、0、假日期或 mock label。
- API failure 不回退 mock；不同 Drawer／Tab 的錯誤彼此隔離。

### 6.3 Page state

- 初次載入、empty、error、retry、pagination、selected-case lazy query 都有明確 presentation。
- A 案切到 B 案時中止 A；A 的晚到 response 不得覆蓋 B。關閉 Drawer／unmount 後不得 set state。
- 已由 server 取得的資料是 read-only；本波禁止 `setOrders` 改變 business status。
- 所有 POST／PUT／PATCH／DELETE 控制在本波保持 disabled／unavailable，不得保留 success alert、confirm
  或 optimistic local mutation。
- 7-stage labels／sections保留，但沒有typed stage projection時，除「全部」外的stage filter與所有stage
  count固定unavailable且不可local filter；Tracker不得把case猜入某stage、複製到每stage或用中文status分類。
- 所有保留surface／control加stable `data-surface-id`／`data-control-id`供component與browser驗收；這只增加
  非視覺測試identity，不授權改版。保留代表可見且可操作導覽，不可`display:none`、zero-size、
  `aria-hidden=true`或opacity 0藏起來。

## 7. Auth 與 runtime boundary

Phase 2A 不修改 Login、session client、Auth backend、token persistence 或 TOTP。它只能使用 Foundation
提供的 authenticated transport。不得使用 dev token、localStorage、combined-login shortcut 或硬編 header
繞過「帳密通過後才進 TOTP」的人工裁決。

真正兩段式 Auth 及可控去敏測試資料未 ready 前，可以完成 client／adapter／component candidate，
但 Work Package 必須標 `blocked` 並列出 `BLOCKED_AUTH_TWO_STEP_CONTRACT`／
`BLOCKED_REAL_BROWSER_EVIDENCE`，不得標 `completed`。

## 8. Positive、negative 與 failure behavior

### Positive

- summary 200 後卡片只顯示該 response 可證明的值。
- 選案後才取得 detail／terms；快速切案始終顯示最新選案。
- empty page 顯示正式空狀態；合法 next cursor 可載入下一頁且不重複。

### Negative

- 任何 schema 缺欄、錯型別、非法日期、非法 ETag 或額外欄位都 fail closed。
- 沒有 stage／SOP／notification／settlement contract 時顯示 unavailable，不讀 mock、不自行推導。
- 點擊任何未接 mutation 控制不得發出非 GET request，也不得改變畫面上的 server-derived status。

### Failure

- 401／403 回 authenticated transport 的既有處置；不把授權失敗顯示成 empty data。
- 404 只用於live route明確宣告的selected-case not found；summary不能把404當空清單，也不得用共用fixture
  創造該route不存在的狀態語意。
- 409／422／503依Contract Scout凍結的endpoint×status/error matrix處理；不存在的status行為不要求、
  不模擬成正式contract。projection conflict不採用partial payload。
- timeout／network error顯示typed retry state；retry不得建立第二份local business state。

## 9. Definition of Done

本波完成代表「Orders／OrderTracker query migration work package 完成」，不代表整個 Orders domain UI
production-ready。全部條件同時成立才可將 Work Package 標 `completed`：

1. Contract-first matrix 已 freeze 且每個 visible field 有 disposition。
2. 兩頁與其 production client／adapter不再引用 `mockData`、`MOCK_ORDERS`、`MOCK_STAFF` 或固定通知。
3. 四個 Orders Drawer、Tracker 雙 Tab 與 11-step 外觀仍存在；缺 contract surface顯示 unavailable。
4. 無 `calculateRefund`、前端日期／coverage／stage／settlement 公式及 local fake mutation。
5. required client、adapter、component tests涵蓋 success、empty、schema mismatch、auth、timeout、abort、stale。
6. lint、build、完整 Vitest、focused backend query regression、write-set audit、UTF-8、header、secret scan、
   `git diff --check` 皆使用 candidate freeze 後的 raw output。
7. 以真 FastAPI、真 React dev server、真正兩段式登入完成去敏 browser smoke，並比對 Network response 與 DOM。
8. Integration Owner 更新原 Work Package、evidence index與所有 blocker；不得只交截圖或代理摘要。

若第 7 項被 Auth 或測試資料阻擋，狀態只能是 `blocked`；文件中另記錄已完成的 candidate evidence，
不能創造 `victory`、`implemented-awaiting-*` 等非專案狀態。

## 10. 明確禁止的虛假完成證據

- 只有 `npm run build`／`npm run lint`／API 200／截圖。
- 移除 `MOCK_ORDERS` 後把相同 literals複製到 page、adapter、test fixture或 CSS。
- 所有內容都顯示 empty／unavailable，卻宣稱既有 UI 已完整 real-data。
- 靜態 11-step status、固定兩筆通知、前端 stage／settlement／coverage／退款公式。
- component mock client 使用 live Pydantic／route 不存在的自創欄位。
- raw dict 只驗 envelope，`data` 經 assertion 或 passthrough 進 component。
- 隱藏／刪除 Drawer、SOP、Notification Tab 來讓驗收通過。
- 留下可點擊的 `alert()`／`confirm()` 假成功或 `setOrders` business mutation。
- 使用繞過兩段式 TOTP 的 dev token／storage／combined-login 後宣稱 browser verified。
- 引用舊 HEAD、舊測試數或另一代理的「passed」文字，沒有 final raw output。

## 11. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | `PASS` | specification 明確禁止 backend／schema／DB write |
| Change inventory | `NOT_RUN` | 無 schema、seed、backfill、destructive change |
| Static release gate | `NOT_RUN` | 不建立 release artifact |
| Descriptor gate | `NOT_RUN` | 不變更 DB object |
| Read-only plan gate | `NOT_RUN` | 不執行 migration plan |
| Engine verification gate | `NOT_RUN` | 不以 React query 接線擴張 DB scope |
| Developer acceptance gate | `NOT_RUN` | 不操作任何既有資料庫 |

總結：`DB_CHANGE_NOT_READY`；本規格不需要也不允許 DB mutation。
