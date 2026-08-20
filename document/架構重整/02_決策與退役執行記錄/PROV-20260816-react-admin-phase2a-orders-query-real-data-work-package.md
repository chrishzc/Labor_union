---
doc_type: work-package
declared_status: blocked
identity: PROV-20260816-react-admin-phase2a-orders-query-real-data
owner: global-admin-web-presentation / orders-query
base_ref: ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922
date: 2026-08-16
revision: V3
specification: PROV-20260816-react-admin-phase2a-orders-query-real-data-specification
approved_by: human-owner
approved_at: 2026-08-16
approval_scope: exact-phase2a-query-only-write-set-and-gates
active_blockers:
  - BLOCKED_REAL_BROWSER_EVIDENCE
---

# React 管理端 Phase 2A：Orders／OrderTracker Query Real-data 工作包（V3，防偷懶版）

## 1. 目標

依同目錄的
`PROV-20260816-react-admin-phase2a-orders-query-real-data-specification.md`，保留已確認的 React
`OrdersPage`、`OrderTrackerPage`、Drawer、Tab、卡片與 11 步 SOP 視覺，把可由 current contract
證明的 `MOCK_ORDERS`／內嵌詳情換成 runtime-validated real API query；缺 contract 的區塊改為
明確 unavailable，不以 mock 或前端推導補齊。本包不重新設計 UI，也不接任何 mutation。

狀態是 `blocked`。2026-08-16 已取得人工對此 exact Work Package 的明確核准；G1–G4 已由
current candidate重新驗證，G5仍缺真正帳密→TOTP登入後的Network↔DOM證據，因此不得標完成。

### 1.1 補強授權邊界

可在不另行請示下補強 evidence、negative tests、反作弊掃描、代理 prompt、receipt、錯誤隔離、
可觀察性與 fail-closed gate，但不得藉「補強」擴張 production scope。下列任一項都必須停止施工並
取得新的人工核准：backend／public API、DB／schema、Auth／TOTP／session、mutation、其他頁面、
UI 重設、shared transport／package dependency 等共享 hot spot、Streamlit／launcher／deployment、
外部 LINE 副作用，或本包未列出的 production path。驗證補強不得以新增自創 contract 取代 live evidence。

## 2. 前置條件與獨立 blocker

- Foundation build／lint／component tests 必須在最新 candidate 通過。
- Contract Scout 必須先交付逐 visible-field matrix，Integration Owner freeze 後其他 writer 才能開工。
- Auth 另依 Access Control 工作包完成真正兩段式 `password challenge → TOTP → Session`。Phase 2A
  可先完成 client／adapter unit tests，但 browser E2E 與 release readiness 在
  `BLOCKED_AUTH_TWO_STEP_CONTRACT` 清除前不得宣稱通過。
- Streamlit Orders 入口維持 active rollback；本包不修改 entry queue、launcher、CORS 或 deployment。

## 3. 人工業務裁決（只供顯示，不在 React 重算）

1. 客戶正式推薦預設只能是一位月嫂；只有單一月嫂無法覆蓋全部日期時，才允許把 2–4 位月嫂的
   分段方案作為一個整體正式推薦。React 只顯示 server view，不自行判斷 coverage。
2. 服務完成、客戶款項結清、月嫂薪資核銷是三個獨立狀態，不合併成單一 settlement／完成 Badge。
3. 缺少緊急聯絡電話只顯示 warning，仍可繼續媒合；不得成為 disabled predicate。

若 live API 無法表達上述資料，回報 `BACKEND_GAP`，不得在 adapter 補公式或以 mock 代替。

## 4. In scope query

| React surface | API 起點 | 接線責任 |
|---|---|---|
| Orders 列表／卡片 | `GET /api/v1/orders/summaries` | 分頁、loading、empty、error、canonical status；warning split尚無contract |
| Orders 詳情 Drawer | `GET /api/v1/orders/{case_no}` | 以 selected case lazy query；切案時 abort 舊請求 |
| 日期只讀資訊 | `GET /api/v1/orders/{case_no}/calendar-detail` | 本波只能顯示typed `service_mode`，不得創造日期／排班facts |
| 條款／表單上下文 | `GET /api/v1/orders/{case_no}/form-management-context` 與 terms query | 填入既有 Drawer read-only 區塊 |
| Actual Start read | `GET /api/v1/orders/{case_no}/actual-start` | 只顯示 current/planned start及版本，不執行Preview／Apply |
| Contract readiness read | `GET /api/v1/orders/{case_no}/contract-completion` | 顯示contract／deposit readiness與blockers，不推三結清 |
| Effective assignment read | `GET /api/v1/orders/{case_no}/assignment-plan` | 顯示server segments；不得稱為客戶formal recommendation |
| OrderTracker | 上述 Orders queries | 保留 7 階段與 11 步外觀；目前沒有 typed stage／SOP view 的動態資料固定 unavailable |
| LINE 通知 Tab | 本波不接 raw／dirty candidate route | 保留 Tab 並標示 unavailable；不得保留固定兩筆通知或 manual replay 假成功 |

raw `dict` route不得進Phase 2A。本波只使用第4節列出的typed endpoints；任何raw／dirty candidate route
固定觸發`PUBLIC_CONTRACT_CHANGE_REQUIRED`，未取得新的人工exception前不得以client Zod自行擴scope。

## 5. Exact write set

- `ui_react/src/api/orders/order_query_schemas.ts`
- `ui_react/src/api/orders/order_query_client.ts`
- `ui_react/src/api/orders/order_query_errors.ts`
- `ui_react/src/adapters/orders/order_summary_adapter.ts`
- `ui_react/src/adapters/orders/order_detail_adapter.ts`
- `ui_react/src/adapters/orders/order_tracker_adapter.ts`
- `ui_react/src/pages/OrdersPage.tsx`
- `ui_react/src/pages/OrderTrackerPage.tsx`
- 僅在 loading／empty／error 需要時修改 `OrdersPage.css`、`OrderTrackerPage.css`
- `ui_react/src/tests/orders_query_client.test.ts`
- `ui_react/src/tests/orders_adapter.test.ts`
- `ui_react/src/tests/orders_page_real_data.test.tsx`
- `ui_react/src/tests/order_tracker_real_data.test.tsx`
- `ui_react/src/tests/orders_no_fake_mutation.test.ts`
- `ui_react/src/tests/fixtures/orders/order_query_contract_fixtures.ts`
- 本工作包與對應 evidence 文件／索引列

禁止修改：`mockData.ts`（只移除本兩頁 import）、其他 9 個業務頁、共用 Drawer／Shell、backend、
schema／migration、Streamlit、launcher、package／lockfile、Git／部署。發現必要變更時停止並提出最小
exception，不擴大本包。

## 6. 多代理分工與防幻覺門檻

| Lane | Owner | 可寫範圍 | 必交 evidence |
|---|---|---|---|
| A Contract Scout | read-only | 無 | current route、response model、測試存在性與 HEAD 行號；不得以 route 存在推論 ready |
| B API Client | client writer | `src/api/orders/`、client test | 真 response fixture、schema reject、401、timeout、abort |
| C Page Adapter | page writer | `src/adapters/orders/`、兩頁 TSX/CSS | before／after mock import、loading／empty／error、drawer 切案 stale test |
| D Verification | read-only auditor | 無 | 重跑 raw commands；不得引用其他代理的「passed」文字 |
| Integration | sole shared writer | 文件／索引與衝突整合 | current diff、write-set audit、最後一次完整驗證 |

任何代理不得把 alert 消失、build 成功、API 200、移除 mock import 或全畫面 unavailable 當作業務正確。
沒有 raw command output、測試名稱、目前 revision 與 exact path 的主張一律標 `unverified`。

## 7. Acceptance

1. 兩頁正常路徑不再 import `../api/mockData`，也不含固定訂單、固定通知或前端 lifecycle 公式。
2. 原 UI hierarchy、卡片、Drawer、Tabs、SOP 呈現與 Desktop baseline 保持；差異只限真資料狀態。
3. 每個query有success、合法empty／nullable、typed schema mismatch、timeout、abort與stale-response tests；
   HTTP error依freeze的endpoint×status/error matrix逐項驗證，不創造route不存在的status語意。summary另有
   cursor、body `etag` decode、append dedupe與query-change abort；本波不實作If-None-Match／304。
4. 快速切換訂單時，舊 response 不得覆蓋新 Drawer；卸載後不得 set state。
5. 電話、地址及其他個資只顯示 server 已授權／遮罩的 view，不把 raw payload寫入 console、DOM hidden
   field、snapshot 或 error。
6. 三項人工裁決有 negative component tests：缺 server contract 時顯示 unavailable，React 不自行建立
   recommendation／三結清／emergency warning，也不以缺電話阻擋本波的唯讀 presentation。
7. `npm run lint`、`npm run build`、`npm test` 全部 exit 0；actual counts 取自 final raw output。
8. focused backend query tests至少包含 `test_order_summary_query.py`、`test_order_detail_query.py`；只讀執行。
9. `git diff --check`、strict UTF-8、source header 與 secret scan 通過。
10. 真 FastAPI／React／兩段式登入 browser smoke 必須比對 Network response 與 DOM；Auth 或測試資料
    blocker 未清除時，Work Package 狀態只能標 `blocked`，不得標 `completed`／`victory`。

## 8. Out of scope

- 新建訂單、候選池、正式推薦、日期確認、條款 Apply、取消、reopen、重送通知等所有 mutation。
- 新增／修改 backend route、response model、DB schema 或資料。
- 重畫 Orders／Tracker UI，或將 11 步 SOP 強制改成單一後端 state machine。
- Streamlit cutover／retirement、部署與正式外部副作用。

## 9. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | `PASS` | 本包明確為 React query-only；禁止 DB write set |
| Change inventory | `NOT_RUN` | 無 schema、seed、backfill 或 destructive change |
| Static release gate | `NOT_RUN` | 不建立 migration release |
| Descriptor gate | `NOT_RUN` | 不變更 DB object |
| Read-only plan gate | `NOT_RUN` | 本包不執行 DB migration tooling |
| Engine verification gate | `NOT_RUN` | 不以 UI query 接線擴張成 DB gate |
| Developer acceptance gate | `NOT_RUN` | 不操作任何 developer／validation／production DB |

總結：`DB_CHANGE_NOT_READY`；本包不需要也不允許 DB mutation。

## 10. 執行拓譜、順序與共享 hot spots

本包使用「Coordinator＋Contract Scout＋API Writer＋Adapter／Page Writer＋fresh Verifier」。
代理不是越多越好；只有唯讀 discovery 可以平行。production writer 依 contract freeze 順序施工。

```text
Gate A  Contract/Gap Scout（read-only）
  ↓ Integration freeze field matrix
Gate B  Orders API Client Writer
  ↓ client schema/tests frozen
Gate C  Adapter + Page Writer
  ↓ candidate freeze
Gate D  Evidence Verifier（read-only fresh context）
  ↓ findings 回唯一 writer修正後重新 freeze
Gate E  Integration Owner 更新 evidence／status
```

互斥寫入規則：

| Role | Exact write set | 禁止 |
|---|---|---|
| Contract Scout | 無；只交 chat handoff | 不修改 source／docs，不以 route 存在判斷 ready |
| Orders API Writer | `ui_react/src/api/orders/**`、`orders_query_client.test.ts` | pages、adapter、shared transport、package／lockfile |
| Adapter／Page Writer | `ui_react/src/adapters/orders/**`、兩頁 TSX／必要 CSS、fixture與其餘四個指定 tests | backend、其他頁、shared shell／Drawer、mockData本體 |
| Evidence Verifier | 無 | 不修 code、不引用其他代理摘要作 evidence |
| Integration Owner | 本 Work Package、specification、02 README、03 evidence／index | 不替未通過 gate 宣告完成 |

`package.json`、`package-lock.json`、shared transport、App、MasterLayout、Drawer、backend、schema、正式索引皆是
shared hot spots／禁止範圍；發現需要修改時停止並提出 exact exception，不能自行擴張。

## 11. Contract Scout 必交 artifact

Scout handoff 必須包含：

1. branch、HEAD、dirty paths保護聲明。
2. 每個 visible field 的 `endpoint + JSON path + server schema + disposition`。
3. 查明 summary／detail／calendar／terms 的 auth、error、cursor、ETag與nullable semantics。
4. 明列 `BACKEND_GAP`：7-stage、SOP、notification、三結清、formal recommendation、emergency warning
   及卡片缺欄；不得把 gap 靜默丟給 page writer。
5. exact focused backend tests與尚未存在的 route-envelope test evidence。
6. N+1、PII、raw dict、dirty candidate與跨 bounded-client風險。

Integration Owner 未明確回覆 `CONTRACT_MATRIX_FROZEN` 前，其他 production writer 必須停止。

## 12. 可直接交付其他模型的 Coordinator Prompt

下列 prompt 是本包唯一建議入口。使用時必須連同本規格與 Work Package exact paths交給協調模型，
不得只貼摘要。

```text
你是 D:\project\Labor_union 的 Phase 2A Integration Owner。你的任務不是重畫 UI，而是依：
1) document/架構重整/02_決策與退役執行記錄/
   PROV-20260816-react-admin-phase2a-orders-query-real-data-specification.md
2) document/架構重整/02_決策與退役執行記錄/
   PROV-20260816-react-admin-phase2a-orders-query-real-data-work-package.md
把現有 OrdersPage／OrderTrackerPage 的 mock query 換成 current typed real API。

先讀 AGENTS.md、README、開發者導覽、Global／Orders／Scheduling／Contract Signing正式規格。
記錄 branch、HEAD、git status --short；所有 dirty／untracked檔案都是使用者成果，禁止 reset、clean、
stash、checkout、覆蓋或刪除。不得 commit、push、建 PR。

不可變規則：
- 保留目前 UI、4 個 Orders Drawer、Tracker雙Tab、7階段導覽與11步SOP外觀；禁止重新設計、刪除或隱藏。
- 本波只做 GET query。所有 mutation控制保留位置但 disabled/unavailable；禁止 alert/confirm假成功、
  setOrders business mutation、calculateRefund及前端日期／stage／coverage／settlement公式。
- 一般正式推薦一位；只有 server證明單人無法完整覆蓋，才把2–4分段作一個正式推薦。
- 服務完成、客戶結清、月嫂薪資核銷是三個獨立projection。
- 緊急聯絡電話缺漏只warning，不阻擋媒合。
- 缺typed contract時顯示 unavailable並記BACKEND_GAP；禁止mock fallback、自創欄位、raw dict穿透、
  unknown as、passthrough或只驗BaseResponse。
- 不修改 backend、DB、schema、Streamlit、Auth、shared shell、package／lockfile或其他九頁。

多代理順序：
A. 先派一名唯讀 Contract Scout，交逐visible-field matrix及exact source/test證據。
B. 你確認並明確輸出 CONTRACT_MATRIX_FROZEN 後，才派 Orders API Writer；其write set只有
   ui_react/src/api/orders/** 與 orders_query_client.test.ts。
C. Client freeze後才派 Adapter/Page Writer；其write set只有工作包第10節列出的paths。
D. Candidate freeze後派fresh Evidence Verifier；Verifier只讀、重跑raw commands，不修code。
E. Verifier finding只能回唯一writer修正；每次修正使舊evidence失效，必須重新freeze與驗證。

任何代理若發現 public contract、backend、schema、Auth、shared hot spot或write set外修改才可完成，
立即停止並回報 exact blocker，不得自行擴張。代理說「passed」不是證據；Coordinator必須親自讀final diff
與raw output。

禁止提前完成：build/lint綠、API 200、移除MOCK_ORDERS、畫面截圖、全部unavailable、mock fetch tests、
舊HEAD測試數，都不能單獨證明完成。只有 specification第9節全部通過才可標completed；Auth／browser／
測試資料未ready時狀態必須blocked並列出 blocker code。
```

## 13. 最終驗收命令與 evidence ledger

候選 freeze 後，Verifier／Integration Owner 必須在 current working tree 執行並保存 raw output；命令可按
環境調整換行，但不得省略範圍。

```powershell
cd D:\project\Labor_union\ui_react
npm test -- src/tests/orders_query_client.test.ts
npm test -- src/tests/orders_adapter.test.ts
npm test -- src/tests/orders_page_real_data.test.tsx
npm test -- src/tests/order_tracker_real_data.test.tsx
npm test -- src/tests/orders_no_fake_mutation.test.ts
npm run lint
npm run build
npm test

cd D:\project\Labor_union
.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests/test_order_summary_query.py `
  tests/test_order_summary_api_client.py `
  tests/test_order_detail_query.py `
  tests/test_order_detail_query_repository.py `
  tests/test_order_detail_ui_client_boundary.py `
  tests/test_order_calendar_detail_query.py `
  tests/test_order_calendar_detail_api_client.py `
  tests/test_order_terms_api_client.py `
  tests/test_order_actual_start_api_client.py `
  tests/test_contract_completion_workflow.py `
  tests/test_assignment_plan_workflow.py `
  --basetemp .pytest_tmp/phase2a-orders-focused -q

rg -n "mockData|MOCK_ORDERS|MOCK_STAFF|calculateRefund" `
  ui_react/src/pages/OrdersPage.tsx `
  ui_react/src/pages/OrderTrackerPage.tsx `
  ui_react/src/api/orders `
  ui_react/src/adapters/orders

git diff --check
git diff --name-only
```

Evidence ledger 至少記錄：candidate HEAD、dirty baseline、實際changed paths、每條命令 exit code、實際
test files／test count、strict UTF-8、source header、secret scan、mock/fake-handler scan、未跑項目、browser
Network／DOM去敏比對與所有 blocker。focused backend tests只證明既有 query邊界，不能替代 React live browser。

## 14. Browser smoke

在 Auth 與去敏測試資料 ready 後：

1. 啟動 FastAPI `127.0.0.1:8000` 與 React dev server `127.0.0.1:5173`。
2. 走真正 `password challenge → TOTP → Session`，不可使用 dev token或 storage shortcut。
3. 開啟 `/#orders`，確認 Network 的 summaries 200與DOM case／status一致。
4. 點選案件後才出現 selected-case detail／terms query；快速 A→B 後 B 保持顯示。
5. 重新整理後重新查 API，不從 mock／storage還原訂單。
6. 驗證所有未接 mutation不發出 POST／PUT／PATCH／DELETE。
7. receipt、截圖與log去敏，不保存 bearer token、完整電話、地址或 raw payload。

沒有以上真 browser evidence 時，即使所有 Vitest、lint、build與backend tests通過，狀態仍不得標
`completed`。

## 15. 逐檔責任與預期結果

代理不得看到目錄級 write set 後自行發明架構。以下是每個檔案的唯一主要責任；若 current source 已有
同等能力，優先最小修改，不得為符合檔名而複製知識。

| Path | 必須提供 | 禁止內容 |
|---|---|---|
| `src/api/orders/order_query_schemas.ts` | Orders-local strict envelope；summary、detail、calendar、terms、actual-start、contract-completion、assignment-plan 的 strict Zod schemas與輸出型別 | `.passthrough()`、catch-all、`z.any()`、`unknown as`、UI labels、business mapper |
| `src/api/orders/order_query_errors.ts` | 只在 shared typed errors不足以表達 Orders query時提供最小 bounded error分類；否則直接重用 | 第二套 transport、解析中文message決定流程、吞掉schema mismatch |
| `src/api/orders/order_query_client.ts` | typed GET methods、safe case encoding、cursor/query/body etag、AbortSignal、既有authenticated transport composition | If-None-Match/304、直接`fetch()`、第二套transport、POST/PUT/PATCH/DELETE、token storage、mock fallback、N+1 preload |
| `src/adapters/orders/order_summary_adapter.ts` | summary DTO → card list presentation；nullable／unavailable discriminant | 7-stage推導、contract amount改名、完整地址／電話補值 |
| `src/adapters/orders/order_detail_adapter.ts` | selected-case query composition及各Drawer read-only sections | 日期／退款／coverage／readiness公式、跨Domain成功推導 |
| `src/adapters/orders/order_tracker_adapter.ts` | 保留7-stage／11-step presentation slots，僅填入server可證明值 | `order_status`→7-stage mapping、固定SOP status、固定通知、三結清合併 |
| `src/pages/OrdersPage.tsx` | loading/empty/error/retry/pagination、selected-case lazy query、原4 Drawers、原action位置unavailable | `MOCK_*`、`setOrders` business mutation、`calculateRefund`、成功alert/confirm、刪Drawer |
| `src/pages/OrderTrackerPage.tsx` | real summary來源、原stepper/sections/雙Tab/Drawer、unsupported-state presentation | fixed notification records、mock checklist state、stage/count推算、manual replay假成功 |
| 兩頁 CSS | 只允許loading/empty/error/unavailable/disabled及既有layout維持所需樣式 | 全面重排、換design tokens、隱藏unsupported區塊、以CSS藏假control |
| `orders_query_client.test.ts` | strict decoder、URLs、headers、cursor/body etag、凍結error matrix、timeout、abort | 304假測試、只有happy path、使用live不存在欄位的fixture |
| `orders_adapter.test.ts` | 每個READY欄位及每個BACKEND_GAP的mapping／negative assertions | snapshot-only、用adapter計算business state |
| `orders_page_real_data.test.tsx` | loading/empty/error/retry/pagination/detail lazy/stale/unmount、4 Drawers、zero mutation | 只測文字存在、刪除原controls後通過 |
| `order_tracker_real_data.test.tsx` | stepper/sections/SOP/notification原位、缺contract unavailable、selected-order isolation | 固定records、由status猜stage |
| `orders_no_fake_mutation.test.ts` | 靜態＋行為證明無mock／公式／business local mutation，未接controls零非GET request | 只做容易改名躲過的單一regex |
| `fixtures/orders/order_query_contract_fixtures.ts` | synthetic success/empty/nullable/extra/missing/wrong-type variants與provenance註解 | production/validation DB資料、真姓名電話地址、從mockData複製或自創server欄位 |

所有新建或修改的 manually maintained source file 依 `coding-rule` 具唯一、正確位置、繁體中文且不超過
150 Unicode字元的 `File`／`Description` header。Markdown、generated output、lockfile不強迫加入source header；
本包禁止修改lockfile。

## 16. 子代理完整 prompts

Coordinator 必須把目前 Task Charter revision、base HEAD、dirty baseline、規格／工作包路徑與以下完整
角色 prompt一起交付；不得只說「請接API」或「請驗收」。

### 16.1 Contract／Gap Scout Prompt（read-only）

```text
角色：Phase 2A Context/Contract Scout，只讀，不可修改任何tracked/untracked檔案。

先讀AGENTS.md、README、開發者導覽、Global/Orders/Scheduling/Contract Signing正式規格，以及Phase2A
specification/work-package。記錄branch、HEAD、git status --short；dirty成果全部保留。

逐一完整讀取OrdersPage.tsx、OrderTrackerPage.tsx、mockData.ts與所有候選route/schema/application/test。
輸出逐visible-field matrix：surface、UI field、mock source、exact endpoint、JSON path、Pydantic schema、
auth/error semantics、test evidence、READY_TYPED/CLIENT_DECODER_REQUIRED/PRESENTATION_CONSTANT/
BACKEND_GAP/OUT_OF_SCOPE_MUTATION。

逐項驗證route+response model+application+focused tests；任何一項缺失不得標READY。raw dict、dirty route、
未註冊route、只有Python client、只有測試檔、只有UI caller都不是typed-ready。明列N+1、PII、跨bounded
client與deprecated/410風險。不得提出UI重設計或backend實作。

交付Context Map、unresolved questions、建議freeze matrix與exact source lines。不要執行會寫cache/dist的
命令。若規格與live code不一致標live-drift，不自行選邊。
```

### 16.2 Orders API Client Writer Prompt

```text
角色：Phase 2A Orders API Client Writer。只有Coordinator明確發布CONTRACT_MATRIX_FROZEN才可開始。
Exact write set只有：
- ui_react/src/api/orders/order_query_schemas.ts
- ui_react/src/api/orders/order_query_errors.ts
- ui_react/src/api/orders/order_query_client.ts
- ui_react/src/tests/orders_query_client.test.ts

先確認current HEAD與freeze matrix仍一致；任一route/schema/base drift立即停止並回報BASE_DRIFT。
使用既有authenticated transport，不修改shared transport/package/lockfile。建立Orders-local strict envelope
與每個DTO strict schema；unknown envelope/DTO fields、missing/wrong/null/invalid date/negative/invalid ETag
均須negative tests。支援cursor、query、body etag、case URL encoding、AbortSignal、timeout與freeze matrix
宣告的typed errors。每次method call即時讀取`sessionClient.getToken()`；缺token以bounded error在request前
fail，token切換／logout不得沿用舊token。不得實作If-None-Match/304、任何non-GET、storage、mock fallback、
第二套transport或UI mapper。

完成前執行focused client test、lint/type/build所需最小命令、header/UTF-8/secret/diff-check。交付Change
Receipt：changed paths、每檔責任、contract impact、raw commands+exit code+actual tests、未跑項目、risks。
沒有raw output不得寫passed；不得commit/push。
```

### 16.3 Adapter／Page Writer Prompt

```text
角色：Phase 2A Adapter/Page Writer。只有client candidate freeze並由Coordinator提供API types/tests證據後開始。
只能修改Work Package第15節列出的3個adapter、2頁TSX、必要CSS、contract fixture及4個指定
adapter/page tests；不得修改API client、shared shell/Drawer、mockData本體、其他頁、backend、Auth、
package/lockfile。

保留現有UI hierarchy、4 Orders Drawers、Tracker stepper/sections/雙Tab/11步labels與所有action位置。
READY欄位映射real DTO；BACKEND_GAP原位顯示明確unavailable，不填0/空字串/假日期/假狀態。
列表cursor append去重；selected-case才lazy query；A→B、close、unmount都abort並有generation guard。
所有未接mutation控制disabled且有原因；點擊不得發出non-GET、不得setOrders改business state、不得success
alert/confirm。刪除calculateRefund、固定通知、mock SOP status、固定日期/金額與MOCK_STAFF候選。

測試必須以schema-valid synthetic fixtures，禁止真個資。不得用自創server欄位、snapshot-only或隱藏/刪除
surface通過。完成前執行5個focused frontend tests、lint/build/full test、mock/fake-handler scan、header、
UTF-8、secret、diff-check。交付Change Receipt；不得宣稱browser/real API已驗證，除非親自執行並有receipt。
```

### 16.4 Fresh Evidence Verifier Prompt（read-only）

```text
角色：Phase 2A fresh Evidence Verifier。candidate freeze後才開始；只讀，不修改任何檔案。
不要接收writer的結論為真，從current HEAD/status/diff/source/raw commands重新驗證。

檢查：exact write set、所有原UI surface仍存在、READY欄位有live schema provenance、BACKEND_GAP原位
unavailable、零mock fallback、零business formula、零fake mutation、strict Zod、auth/abort/stale/error tests、
source headers、UTF-8、secret、PII、git diff --check。重跑Work Package第13節命令並記actual counts/exit code。

主動嘗試反證：把unknown field餵decoder、晚到A response覆蓋B、點每個未接action監看non-GET、搜尋
MOCK_/Math.random/new Date/calculateRefund/alert/confirm/setOrders/unknown as/passthrough/z.any。
browser前置不具備時標BLOCKED，不得用happy-dom或截圖替代。

輸出Evidence Bundle：PASS/BLOCKED/NOT_RUN逐項表、raw evidence locator、scope violations、findings與最小
修正建議。任一P0/P1 finding即不得建議completed。不得修code、commit或更新文件。
```

## 17. Task Charter 與 handoff 模板

Coordinator 開工時建立並在每次material discovery後遞增 revision；未同步revision的代理輸出作廢。

```text
Task Charter Revision: PHASE2A-R<n>
Base: branch=<branch>, HEAD=<sha>, dirty-baseline=<保存位置或完整摘要>
Authorized outcome: Orders/Tracker query foundation，保留既有UI
In scope: specification §5 READY_TYPED + work-package exact write set
Out of scope: all mutation/backend/schema/Auth/other pages/shared hot spots
Invariants: formal recommendation、三結清、warning-only、UI preservation、zero fake success
Known gaps: <matrix BACKEND_GAP rows>
Active blockers: <codes>
Sole integration writer: <agent>
Candidate freeze marker: <timestamp/revision; 不使用內容hash當任務identity>
Required evidence: <command matrix + browser receipt>
Stop conditions: base drift/public contract/write-set expansion/security/PII/destructive action
```

Writer Change Receipt 固定格式：

```text
Role / Charter revision / observed HEAD
Changed paths（逐檔）
Intent per path
Public contract impact
Header language/compliance/exclusions
Commands（原命令、exit code、actual counts、final edit之後執行）
Negative controls performed
Not run / blocked / residual risk
Scope exceptions requested（沒有則寫none）
No commit/push/destructive action confirmation
```

Verifier Evidence Bundle 固定格式：

```text
Charter revision / candidate HEAD / dirty-baseline comparison
Write-set audit: PASS|BLOCKED
Contract provenance: PASS|BLOCKED
UI preservation: PASS|BLOCKED
Mock/formula/fake mutation: PASS|BLOCKED
Client/adapter/page tests: PASS|BLOCKED|NOT_RUN
Lint/build/full tests: PASS|BLOCKED|NOT_RUN
Backend focused regression: PASS|BLOCKED|NOT_RUN
Browser Network↔DOM: PASS|BLOCKED|NOT_RUN
UTF-8/header/secret/PII/diff-check: PASS|BLOCKED|NOT_RUN
Findings by severity with exact path/line
Completion recommendation: completed|blocked（不得創造其他共享status）
```

## 18. Blocker、停止與例外代碼

| Code | 觸發條件 | 必須行為 |
|---|---|---|
| `BASE_DRIFT` | HEAD、schema、route、shared transport或freeze matrix開工後改變 | 停止writer；重讀diff、重做matrix／Charter revision |
| `WRITE_SET_VIOLATION` | 需要或已修改未授權path | 停止；回復僅自己且可安全辨認的未授權變更或交Integration裁決，不碰他人成果 |
| `BACKEND_CONTRACT_GAP` | UI欄位無current typed contract | 原位unavailable；記successor need，不自行修backend |
| `SHARED_TRANSPORT_RESPONSE_METADATA_GAP` | ETag header／304需要status與headers，但current transport只回body | Phase2A不實作If-None-Match/304；不得直接fetch／建第二transport |
| `SHARED_HOTSPOT_REQUIRED` | shared transport/Drawer/App/package等才能完成 | 提出exact exception；未核准前停止 |
| `BLOCKED_AUTH_TWO_STEP_CONTRACT` | 真正password challenge→TOTP→Session不可用 | unit candidate可繼續；browser/completion blocked |
| `BLOCKED_TEST_DATA` | 無去敏、可控real-data case | 不讀production個資；browser/completion blocked |
| `BLOCKED_REAL_BROWSER_EVIDENCE` | 無真FastAPI/Vite/auth/browser證據 | 不用happy-dom/截圖替代；status blocked |
| `PII_OR_SECRET_EXPOSURE` | log/fixture/snapshot/DOM/error含不必要個資或secret | 立即停止、最小化證據並交Integration/security review |
| `PUBLIC_CONTRACT_CHANGE_REQUIRED` | 必須改API/schema/Domain semantics | 本包停止；另立proposed Work Package取得人工核准 |

代理不能以「時間不足」「測試太慢」「大致可行」「其他agent說已過」作為skip理由。無法執行時使用
`BLOCKED`／`NOT_RUN`及exact reason，不得將未執行轉成PASS。

## 19. 防偷懶機械檢查與人工反證

下列掃描只是最低門檻，不能取代behavior tests；改名規避仍由Verifier人工反證。

```powershell
# 禁止的mock／公式／弱型別／假成功候選
rg -n "mockData|MOCK_|Math\.random|calculateRefund|unknown as|\.passthrough\(|z\.any\(" `
  ui_react/src/api/orders ui_react/src/adapters/orders `
  ui_react/src/pages/OrdersPage.tsx ui_react/src/pages/OrderTrackerPage.tsx

rg -n "alert\(|confirm\(|setOrders\(|fetch\(" `
  ui_react/src/pages/OrdersPage.tsx ui_react/src/pages/OrderTrackerPage.tsx

# 原UI surface存在性；每一項還須component behavior test
rg -n "Drawer|stepsChecklist|notifications|orders-filter-bar|matching|cancel" `
  ui_react/src/pages/OrdersPage.tsx ui_react/src/pages/OrderTrackerPage.tsx

# production client只能GET；Verifier另以transport spy證明
rg -n "POST|PUT|PATCH|DELETE" ui_react/src/api/orders ui_react/src/adapters/orders
```

Verifier 必須再人工檢查：

1. literals 是否改名搬到adapter/test fixture，而非真正來自API。
2. unavailable 是否只覆蓋真正 gap，而不是偷懶吞掉 `READY_TYPED`。
3. disabled 是否真阻止event/request，而非CSS灰色但handler仍執行。
4. 11-step labels仍存在，但status/timestamp/notes沒有mock。
5. summary沒有N+1 detail；selected-case tabs error隔離。
6. tests是否由同一錯誤implementation自創contract，必須反查live Pydantic schema。
7. command output是否在最後相關edit之後、current candidate上執行。

## 20. Integration Owner 最終裁決表

| Gate | Pass condition | Fail disposition |
|---|---|---|
| G0 Authority | exact Work Package已人工核准；Charter revision current | 未核准不得開production writer |
| G1 Contract | field matrix逐欄freeze且base無drift | 回Contract Scout |
| G2 Client | strict decoder與所有failure tests通過 | 回API Writer |
| G3 Presentation | 原UI保留、real data接線、gap原位unavailable、零fake mutation | 回Page Writer |
| G4 Static/Test | focused＋full tests、lint/build、quality scans fresh | 回唯一writer後全部受影響evidence重跑 |
| G5 Runtime | 真Auth、真API、真DOM、zero non-GET browser smoke | 狀態`blocked`並列code；不得倒推G1–G4免做 |
| G6 Evidence | evidence index、raw outputs、actual counts、residual gaps完整 | 不得completed |

只有G0–G6全部PASS，且沒有P0/P1 finding、scope violation、未裁決public contract或required NOT_RUN，
Integration Owner才可將原Work Package改為`completed`。完成聲明必須同時寫明「本包只完成query
foundation，哪些UI仍因BACKEND_GAP unavailable」，禁止使用`victory`掩蓋後續backend／mutation工作。

Auth、test-data或browser blocker只影響G5/G6。即使它們已知會阻擋completed，G1 Contract、G2 Client、
G3 Presentation、G4 Static/Test仍必須執行並PASS；用`BLOCKED_AUTH_*`交付G1–G4 `NOT_RUN`固定視為
`REJECTED_HANDOFF`，不能把runtime blocker當不施工理由。

## 21. Durable evidence artifacts 與 freeze receipts

Contract matrix與驗收不得只存在於聊天摘要。Integration Owner是唯一文件 writer，將各read-only角色的
handoff逐項比對source後，寫入下列 provisional evidence root：

```text
document/架構重整/03_追蹤清單與證據/evidence/
  PROV-20260816-react-admin-phase2a-orders/
    contract-field-matrix.md
    contract-matrix-freeze-receipt.md
    candidate-change-inventory.md
    verification-receipt.md
    browser-smoke-receipt.md
    open-findings.md
```

這些 evidence 不構成實作授權。每個檔案使用same provisional identity，不自行配canonical ordinal；只有
Integration Owner在最新base上依專案規則late-bind。raw console logs放`scratch/react-phase2a-orders/logs/`
且不提交；versioned receipt只保存去敏、最小、可重跑的命令／結果摘要。

### 21.1 `contract-field-matrix.md`

每列固定欄位，不得用段落摘要取代：

```text
surface_id | control_id | visible_field | current_mock_source | method | endpoint | json_path |
server_schema | source_path:line | focused_test | nullability | pii_class | display_policy |
allowed_http_statuses_and_errors | disposition | page_behavior | positive_test | negative_test |
verified_head | verified_by
```

允許 disposition只有 specification第4節五種值。Integration Owner materialize後，原Contract Scout須
readback核對；不同意時在`open-findings.md`記錄，不能發布freeze receipt。

### 21.2 `contract-matrix-freeze-receipt.md`

至少記錄 Task Charter revision、branch/HEAD、matrix row count、所有source/test path存在性、live-drift、
unresolved rows、Scout readback及`CONTRACT_MATRIX_FROZEN`或`BLOCKED`。HEAD或相關schema/route改變後receipt
立即stale，所有writer停止。

### 21.3 Candidate／verification／browser receipts

每一claim固定包含：

```text
claim_id
status: PASS | BLOCKED | NOT_RUN
command_or_manual_step
started_at / finished_at
exit_code
candidate_head / charter_revision
changed_paths
observed_result（actual counts，不寫「正常」）
evidence_locator
limitations / blocker_code
verifier
```

`candidate-change-inventory.md` 逐檔記意圖與owner；`verification-receipt.md` 保存final candidate gates；
`browser-smoke-receipt.md` 去敏記 Network↔DOM比對與process cleanup；`open-findings.md` 記finding severity、
owner、status、retest。`VICTORY`、`mostly done`、`implemented-awaiting-*`不是合法status。

## 22. Contract fixture provenance

`order_query_contract_fixtures.ts` 只放去敏、deterministic、synthetic HTTP payload；每個export上方註明：

```text
Provenance: <api/schema path + model> @ <verified HEAD>
Purpose: success | empty | nullable | extra-field | missing-field | wrong-type
PII: synthetic; no production/customer data
```

Required variants：

- summary success、empty、nullable dates/staff、next cursor、valid ETag、invalid ETag。
- 每個selected-case query success及其合法nullable fields。
- unknown envelope field、unknown DTO field、missing required field、wrong primitive、invalid date、negative value。
- `success=false`、`data=null`及typed error envelope。

Fixture欄位必須逐一反查current Pydantic model；禁止從`mockData.ts`、production DB、browser response或舊
Streamlit render dict複製。測試不得因schema更新就順手放寬decoder；base drift須回Gate G1。

`display_policy`只能為`DISPLAY | INTERNAL_ONLY | SENSITIVE_REDACTED`。typed不等於可全部顯示：token、
`line_group_id`、internal ids、raw notes及未授權個資不得進DOM、console、snapshot或error。Adapter只處理
`DISPLAY`欄位；測試須證明其餘兩類不外洩。

## 23. 最低 real-data 必達矩陣

下列是Phase 2A不能偷懶標成unavailable的最小正向覆蓋；只有API合法回nullable時才顯示該欄位的
unavailable presentation。

| Surface ID | API JSON path | DOM必須呈現 | Required evidence |
|---|---|---|---|
| `orders.list.card.identity` | `items[].case_no`、`client_name`、`order_status` | 每張卡的案件編號、客戶名、canonical status | success component test＋Network↔DOM browser比對 |
| `orders.list.card.dates` | `start_date`、`end_date`、`actual_start_date`、`service_days` | 非null值原樣呈現；null顯示明確未提供 | nullable negative test |
| `orders.list.card.staff` | `staff_name` | 只標示摘要staff name，不稱正式推薦／正式assignment | semantic assertion |
| `orders.list.card.amount` | `total_employer_self_pay_payable` | 只能使用正式「雇主自付應付」名稱 | 禁止contract total誤標test |
| `orders.detail.core` | selected detail fields | 開Drawer後才顯示case、ids、dates、hours、floor fee等schema欄位 | lazy query＋stale test |
| `orders.detail.terms` | `terms.*` | time tuple、cooking、floor fee、service data lock | strict client＋component test |
| `orders.detail.actual-start` | actual-start query fields | planned／current actual start及lock狀態 | selected-case test |
| `orders.detail.contract` | contract-completion query fields | contract/deposit readiness、domain blockers | 不推三結清test |
| `orders.detail.assignment` | assignment-plan `assignments[]` | sequence、staff id、assigned range／official dates | 不稱formal recommendation test |
| `orders.detail.calendar` | calendar-detail `service_mode` | 只顯示service mode | 不創造calendar dates test |

若代理把以上任一合法非null READY_TYPED值顯示為unavailable，Gate G3固定`BLOCKED`。相反，5.3 matrix的
BACKEND_GAP不得以fixture自創欄位填滿。

### 23.1 Stable surface／control inventory

Integration Owner於Contract Matrix freeze時，以current JSX逐項確認下列最低identity；允許新增屬性但不改
視覺文案／layout。若實際surface更多，Scout必須補齊，不能以此表是最低集合為由漏記。

```text
surface: orders.page, orders.filters, orders.cards
surface: orders.drawer.date, orders.drawer.matching, orders.drawer.contract, orders.drawer.cancellation
surface: tracker.page, tracker.stepper, tracker.stage-sections, tracker.drawer
surface: tracker.tab.sop, tracker.tab.notifications

control: orders.create
control: orders.filter.all, orders.filter.stage-1..stage-7
control: orders.card.terms, orders.card.matching, orders.card.date, orders.card.cancel, orders.card.reopen
control: orders.date.send, orders.date.convert
control: orders.matching.add, orders.matching.reset, orders.matching.info-1, orders.matching.info-2
control: orders.matching.willingness, orders.matching.resume-send, orders.matching.customer-decision
control: orders.matching.waiting-lock
control: orders.cancellation.apply
control: tracker.tab.sop, tracker.tab.notifications, tracker.notification.manual-replay
```

Tests逐ID驗證：surface存在、非hidden、Drawer／Tab navigation可開啟；mutation control是native disabled或
等價不可觸發語意、具unavailable reason、沒有business handler。Browser以computed style與bounding rect抽驗
四個Drawer及雙Tab；source中存在但CSS隱藏不算保留UI。

### 23.2 UI action → endpoint request budget

Freeze artifact必須為每個action列`allowed endpoints`、`maximum calls`、cache/retry與abort semantics。最低
約束如下；`maximum calls`是單次正常操作上限，explicit retry／pagination另計且必須由使用者觸發：

| Action | Allowed endpoints | Max normal calls | 禁止 |
|---|---|---:|---|
| Orders initial load | `/orders/summaries` | 1 | detail N+1、任何non-GET |
| Search/query change | `/orders/summaries` | 1 | 舊query晚到覆蓋、新舊結果混合 |
| Next page | `/orders/summaries?after_case_no=...` | 1 | 重複cursor無限循環 |
| Open terms/contract Drawer | selected detail、terms、contract-completion | each 1 | contract-signing raw route、mutation |
| Open date Drawer | selected detail、calendar-detail、actual-start | each 1 | 自算end/buffer、mutation |
| Open matching Drawer | selected detail、assignment-plan | each 1 | candidate/matching raw routes、稱formal recommendation |
| Open cancellation Drawer | selected detail | 1 | cancellation Preview/Apply、退款公式 |
| Tracker initial load | 無typed stage projection時不發stage query | 0 | 用summary status猜stage、複製case |
| Notification Tab | 無核准typed timeline | 0 | raw LINE route、固定通知、manual replay |

相同cursor重播：同case同payload可去重；相同case衝突payload或repeated non-advancing cursor必fail closed，
不得任選first/last wins或持續請求。每個READY_TYPED JSON path至少具一個adapter assertion與兩組不同sentinel
payload的DOM assertion，證明頁面隨response改變而非硬編。

## 24. Handoff rejection、retry 與人工升級

任一代理交付符合下列條件即標`REJECTED_HANDOFF`，不得由Coordinator代寫「passed」補洞：

- 未列current HEAD／Charter revision／dirty preservation。
- 缺exact paths、source evidence、raw command與exit code。
- 修改write set外檔案、shared hot spot、backend或package/lockfile。
- 測試不存在、失敗、未跑卻標PASS，或以刪測試／放寬schema取得綠燈。
- 把READY_TYPED改unavailable逃避實作，或把BACKEND_GAP用mock／前端推導補齊。
- 引用其他代理summary、舊candidate output或未在final edit後重跑的證據。

處理順序：

1. 第一次不合格：Coordinator退回同role，指出exact finding與acceptance。
2. 修正後所有受影響evidence stale，重新freeze／重跑；不得只補一段文字。
3. 同一根因再次出現：停止該lane，使用blocker code並由Coordinator直接檢查source；不得降低門檻。
4. 若根因是public contract、shared hot spot、業務語意衝突或第三次仍無法閉合，停止整包並交人工裁決；
   不得再spawn更多代理投票決定。
5. Contract Scout與writer意見衝突時，以人工裁決→正式規格→live typed source/test precedence處理；無唯一
   答案即`BLOCKED`，不採多數決。

## 25. 補充機械驗收命令

以下在第13節之後執行；PowerShell `rg`「零命中」通常exit code 1，只有exit code 1且stdout為空才算
此類negative scan PASS，exit code>1固定BLOCKED。

```powershell
# Strict UTF-8：對actual changed text paths使用throwOnInvalidBytes解碼；任何例外BLOCKED。
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$trackedChanged = @(git diff --name-only)
$untrackedInScope = @(git ls-files --others --exclude-standard -- `
  ui_react/src/api/orders ui_react/src/adapters/orders ui_react/src/tests `
  document/架構重整/03_追蹤清單與證據/evidence)
@($trackedChanged + $untrackedInScope | Sort-Object -Unique) | ForEach-Object {
  if (Test-Path -LiteralPath $_ -PathType Leaf) {
    $null = $utf8.GetString([IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $_)))
  }
}

# Exact write-set：candidate changed paths逐一比對本Work Package allowlist；未知path固定BLOCKED。
git diff --name-only
git ls-files --others --exclude-standard -- ui_react/src/api/orders `
  ui_react/src/adapters/orders ui_react/src/tests document/架構重整/03_追蹤清單與證據/evidence

# Source header audit：每個changed manually-maintained .ts/.tsx必須唯一File/Description header且payload<=150字。
rg -n "File:|Description:|@file|@description" ui_react/src/api/orders `
  ui_react/src/adapters/orders ui_react/src/pages/OrdersPage.tsx `
  ui_react/src/pages/OrderTrackerPage.tsx ui_react/src/tests

# Secret/PII候選；命中後人工裁決，不可自動忽略。
rg -n "Bearer\s+[A-Za-z0-9._-]{20,}|sk-[A-Za-z0-9_-]{20,}|09[0-9]{8}|完整地址|銀行帳號" `
  ui_react/src/api/orders ui_react/src/adapters/orders ui_react/src/tests `
  document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2a-orders
```

Browser smoke必須記錄API/Vite啟動方式、PID、port、health/readiness、開始／結束時間與cleanup結果。背景
process使用hidden window；只終止本次receipt記錄的PID，不依模糊process name清理，也不得把既有服務誤殺。

### 25.1 Dirty baseline與write-set attribution

開工前Integration Owner在`scratch/react-phase2a-orders/baseline/`保存：完整`git status --short`、各role
authorized既有檔案的原始副本、相關path的`git diff`及untracked存在性清單。這些是ignored暫存，不提交、
不成為task identity，也不以內容hash作owner／衝突裁決。候選freeze後以`git diff --no-index`逐一比較原始副本，
並列新增檔；只有本包allowlist內的delta可歸因本包。

工作包外既有dirty仍屬使用者成果，不能因`git diff --name-only`出現就判違規；但若本包代理使其相對baseline
產生新delta，固定`WRITE_SET_VIOLATION`。若同時有其他已授權lane修改同一路徑，停止並做base-drift／owner
衝突盤點，不能用ours/theirs或檔案時間自行選邊。

### 25.2 Weak-test／mock-laundering scan

```powershell
rg -n "\.skip|\.todo|\.only|expect\.assertions\(0\)|expect\(true\)|snapshot" `
  ui_react/src/tests/orders_query_client.test.ts `
  ui_react/src/tests/orders_adapter.test.ts `
  ui_react/src/tests/orders_page_real_data.test.tsx `
  ui_react/src/tests/order_tracker_real_data.test.tsx `
  ui_react/src/tests/orders_no_fake_mutation.test.ts

rg -n "z\.unknown|z\.record|\.passthrough|z\.any|\.catch\(|\.default\(|\.coerce|\.preprocess|\.transform|unknown as" `
  ui_react/src/api/orders ui_react/src/adapters/orders ui_react/src/tests
```

任何命中需逐項人工裁決；snapshot只能作輔助，不能是唯一assertion。Verifier沿OrdersPage／OrderTrackerPage
完整production import closure確認無直接或間接`mockData.ts`依賴，並從baseline mock抽取案件ID、姓名、電話、
固定日期與通知文案作literal交叉掃描；presentation labels另列allowlist。不能只改變常數名稱規避。

`orders_no_fake_mutation.test.ts`逐一click matrix中的mutation control，以transport及global fetch spy證明
non-GET request總數為0、server-derived DOM不變、control為native disabled且沒有dead fake business handler。
Verifier另依live Pydantic schema自行建立adversarial vectors；writer提供的fixture不能是schema正確性的唯一證據。
