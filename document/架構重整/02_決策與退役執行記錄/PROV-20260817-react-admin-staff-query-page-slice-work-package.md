---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-staff-query-page-slice
date: 2026-08-17
owner: Staff Query / React Integration Owner
domain: Staff
subsystem: Staff Directory Query / React Presentation
initiative: react-admin-migration
prerequisites: PROV-20260817-react-admin-page-slice-migration-execution-decision approved; Phase 2C volatile bearer session runtime available; existing StaffSummaryPageView contract audit complete
approval_required: 核准此 exact Phase 3 Staff Query Page-Slice Work Package
authority: exact-human-approved-2026-08-17
ui_execution_mode: browser-required
delivery_ceiling: query-real-data-validated
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: relevant page, route, schema, client or shared-auth drift requires fresh read and re-freeze before implementation
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
---

# Phase 3：Staff query page-slice 真實資料接線工作包

> Activation：使用者已明確回覆「核准此 exact Phase 3 Staff Query Page-Slice Work Package」。

> Completion：backend 4、React focused 16、full React 517 tests與build通過；真Chrome Staff summaries GET
> 200並進DOM，未提供欄位unavailable、mutation native disabled，0 non-GET。狀態為`completed`。

## 0. 人工裁決與最小目標

本包依已採用的「逐頁精簡遷移模式」建立，唯一目標是把 React `#staff` 的名冊／摘要查詢從
`MOCK_STAFF` 接到既有 bounded `GET /api/v1/staff/summaries`，並在既有 StaffPage 視覺結構中
誠實呈現可用欄位與 unavailable 槽位。

本包不是 Staff domain 全面完成，也不是 Phase 3B1 的 Preferences、Availability、Lifecycle
mutation 包。它不等待、也不解鎖那些工作流；其完成上限固定為 `query-real-data-validated`，不得
宣稱 `Staff master complete`、`Phase 3B1 complete`、entry cutover 或 Streamlit retirement。

操作者是已完成兩段式 TOTP 登入的管理員。查詢根事實只由後端摘要 view 擁有：`id`、`name`、`phone`。
React 不得由資料庫欄位、mock、日期或其他頁面資料補出主檔、證照、技能、偏好、銀行或在職狀態。

## 1. 現況證據與來源邊界

### 1.1 React UI baseline

- `ui_react/src/pages/StaffPage.tsx`：三個既有 tabs、名冊卡片、履歷／證照 Drawer、偏好與不可服務槽位。
- `ui_react/src/pages/StaffPage.css`：既有 Staff grid、tab 與 card 樣式；只做必要的 loading／error／
  unavailable 呈現，不重畫視覺基線。
- `ui_react/src/api/mockData.ts`：保留供其他 baseline pages 使用；本包只要求 `StaffPage.tsx` 移除
  自己的 `MOCK_STAFF` import，不得修改或刪除此檔。

### 1.2 既有 Streamlit／後端參考

- `ui/api_clients/staff_summary_api_client.py`：已存在的 typed HTTP query client，僅作既有 API 使用證據，
  本包不修改。
- `ui/pages/04_finance.py::_load_staff_summaries`、`ui/pages/03_calendar.py` 與
  `ui/pages/scheduling/leave_substitution_panel.py`：既有摘要查詢／選擇器 caller；不把其中的
  page-local presentation 或完整 staff table 欄位當成 `#staff` public contract。
- `ui/pages/01_data_browser.py` 的 `staff`／`staff_bank_accounts`：除錯維運入口，不是 StaffPage 的
  public API，也不授權 React 直接查表或顯示 PII。
- `api/routes/staff.py`、`api/schemas/staff_summary.py`：唯一本包可採用的摘要 endpoint／Pydantic view。

### 1.3 現況缺口

`GET /api/v1/staff/summaries` 目前已有 cursor SQL 與 `StaffSummaryPageView`，但 route 沒有
`require_admin` enabled-principal session guard；`staff_id` 與 `after_id` 同時提供時也以 raw
`HTTPException.detail` 回應。這是本 page 所需的最小 route hardening，直接納入本包，不另建獨立 gap。

Staff master、證照／附件、銀行、區域、技能、問卷、在職狀態、偏好 definitions/profile、不可服務
期間與 lifecycle 均已有相鄰 Phase 3B1／3B1 remaining-controls／3C owner gap routing；本包只在
原 UI 槽位標示 unavailable 或 native disabled，不重複建立 successor。

## 2. Frozen query contract

### 2.1 Endpoint

```text
GET /api/v1/staff/summaries
  ?page_size=1..200
  [&after_id=<positive integer> | &staff_id=<positive integer>]
```

- `after_id` 與 `staff_id` 互斥；不得由 client 同時送出。
- 預設名冊查詢使用 `page_size=200`，由 `id ASC` cursor 前進；不得使用退役的
  `GET /api/v1/staff` 全量 endpoint。
- `staff_id` exact lookup 只有在本頁未來明確需要 deep-link 時才可使用；本包第一版不新增
  deep-link，避免無必要的單筆 burst。

### 2.2 Success payload

後端目前的 public view 必須維持以下 strict shape：

```text
BaseResponse[StaffSummaryPageView]
  success: boolean
  message: string
  data: {
    items: StaffSummaryView[]
    next_cursor: positive integer | null
  }
  error: string | null/omitted

StaffSummaryView
  id: positive integer
  name: string | null
  phone: string | null
```

Frontend Zod schema 必須 `.strict()`，禁止 `.default()`、`z.record()`、`z.any()`、`z.unknown()`、
`.passthrough()`、`.catch()`、`.coerce()`、`.preprocess()`、`.transform()`、`as any` 與
`unknown as`。Backend nullable 欄位只對應 `.nullable()`；不可把缺失資料轉成空字串、0、假 status
或預設姓名。

每一個 `id` 只能出現一次；`next_cursor` 必須向前推進且不得重複已查過的 cursor。違反時 client
fail closed，不自動重試、不合併重複卡片、不以成功空清單掩蓋契約錯誤。

### 2.3 Minimum route hardening

只允許下列最小後端變更，且不改 SQL、DB schema、Domain 或 shared error handler：

1. `api/routes/staff.py::get_staff_summaries` 加入既有 `require_admin` dependency，讓無 Bearer
   session、失效／disabled principal fail closed；所有enabled internal users維持相同業務query能力，root
   不在Staff頁取得額外功能。保留既有 development profile 的正式 auth
   行為，不建立 dev token bypass。
2. `staff_id + after_id` 衝突改用既有 `typed_http_error`／Global envelope 的 validation category、
   穩定 code（例如 `staff_summary_query_params_conflict`）、correlation id 與 field/domain error
   欄位；不得讓 raw中文 `detail` 成為 React 分支依據。
3. 保留既有 `StaffSummaryPageView` `extra="forbid"`、cursor SQL、`internal_query_error` 與退役
   unbounded endpoint；除非逐欄 matrix 證明必要，不擴大 `api/schemas/staff_summary.py` 變更。

這不是 Global FastAPI error boundary 的重構；若 route hardening 需要修改 shared handler、transport、
Global schema 或其他 domain，立即記錄 `SHARED_HOTSPOT_REQUIRED` 並停止該超出範圍變更。

## 3. UI slot disposition

### 3.1 真實接線（wired）

| UI surface | stable `data-control-id`／identity | source | disposition |
|---|---|---|---|
| `#staff` page shell | `staff.page` | existing React route | wired；保留 title、tabs、CSS |
| initial roster load | `staff.directory.query` | one GET summaries | wired；顯示 loading／typed error／empty |
| roster card identity | `staff.card.<positive-staff-id>` | `items[].id/name/phone` | wired；不得改成 `STF-001` 等 mock identity |
| next cursor action | `staff.directory.next-page` | `data.next_cursor` | 只有 server 回 cursor 時顯示；手動觸發一個 GET |
| existing resume drawer open | `staff.drawer.open.<positive-staff-id>` | loaded summary only | wired；不得再猜 detail 或自動呼叫未核准 endpoint |
| drawer close | `staff.drawer.close` | local presentation state | wired；零 API |

`name`／`phone` 為 null 時顯示明確的 `後端未提供` 或 `—`，不可渲染 undefined、假電話或 mock 姓名。
Drawer 標題只可使用 server name；沒有 name 時顯示「服務人員摘要」與正整數 id。

### 3.2 原位 unavailable（保留視覺，不冒充資料）

名冊卡與 Drawer 的下列槽位保留原位置，但值固定為 `後端尚未提供 typed ...`／`—`，不由其他 API、
`mockData` 或 SQL 補值：

- active／請假／暫停狀態、服務區域、實務年資、問卷分數。
- 技能／料理能力、special notes、良民證、體檢、專業證照與證件有效期。
- 履歷、附件、銀行代碼／戶名／帳號與任何完整 PII。
- 證照過期提醒的 fake count、固定姓名與「已阻擋派單」故事；若沒有 typed certification view，
  只顯示「證照提醒：後端尚未提供 typed contract」，不可保留 `1 筆` 等硬編結果。

### 3.3 Native disabled／out-of-scope

以下 control 仍保留視覺位置但必須 `disabled`，加上穩定 id 與 unavailable 說明；點擊不得 fetch、
alert、confirm、prompt 或產生 local success：

- `staff.master.create`、`staff.master.edit`、`staff.master.save`、`staff.master.attachment-upload`、
  `staff.master.bank-edit`、`staff.master.certificate-approve`。
- `staff.preferences.preview`、`staff.preferences.apply`、`staff.preferences.cooking-skills`、
  `staff.preferences.special-notes`。
- `staff.availability.create.preview`、`staff.availability.create.apply`、
  `staff.availability.cancel.preview`、`staff.availability.cancel.apply`、
  `staff.availability.end-pause`。
- `staff.lifecycle.retirement.preview`、`staff.lifecycle.retirement.apply`、
  `staff.lifecycle.reactivation.preview`、`staff.lifecycle.reactivation.apply`。

Tabs `staff.tab.roster`、`staff.tab.preferences`、`staff.tab.unavailability` 可以切換視覺內容；切換
不應發出 API，後兩個 tab 只呈現原位 unavailable／disabled，不得把 Staff summary 冒充完整 profile。

## 4. Exact write set 與禁止越界

### 4.1 本包允許修改

Frontend：

- `ui_react/src/api/staff_directory/staff_directory_schemas.ts`（new）
- `ui_react/src/api/staff_directory/staff_directory_errors.ts`（new）
- `ui_react/src/api/staff_directory/staff_directory_client.ts`（new）
- `ui_react/src/adapters/staff/staff_directory_adapter.ts`（new）
- `ui_react/src/pages/StaffPage.tsx`
- `ui_react/src/pages/StaffPage.css`
- `ui_react/src/tests/fixtures/staff/staff_directory_contract_fixtures.ts`（new）
- `ui_react/src/tests/staff_directory_client.test.ts`（new）
- `ui_react/src/tests/staff_directory_adapter.test.ts`（new）
- `ui_react/src/tests/staff_directory_page.test.tsx`（new）
- `ui_react/src/tests/staff_directory_no_fake_mutation.test.tsx`（new）
- `ui_react/src/tests/staff_directory_request_budget.test.tsx`（new）

Backend minimum hardening：

- `api/routes/staff.py`
- `tests/test_staff_summary_routes.py`（new）

Documentation/evidence：

- `document/架構重整/02_決策與退役執行記錄/PROV-20260817-react-admin-staff-query-page-slice-work-package.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-staff-query-page-slice/`

`api/schemas/staff_summary.py` 是 read-only contract input；只有若 implementation matrix 證明
Pydantic view 與 endpoint response 不一致，才可在本包內做最小 strict schema 修正，並在 evidence
明列欄位與理由。不能藉機改成 Staff master schema。

### 4.2 明確禁止

- 修改 `ui_react/src/api/shared/transport.ts`、`runtime_decoder.ts`、Auth/session client、`App.tsx`、
  `package.json`、`package-lock.json`、`ui_react/src/api/mockData.ts` 或其他 page。
- 修改 DB、schema migration、seed、backfill、Streamlit source、entry registry、Phase 5/6 cutover
  或 retirement 文件。
- 新增 Preferences／Availability／Lifecycle／Leave/Substitution client，或在 StaffPage 直接 fetch。
- 讓 `StaffSummaryView` 的三欄冒充完整 master、資格、銀行或偏好資料。
- 使用 `alert()`、`confirm()`、`prompt()`、`Date.now()`、local fake state、hardcoded staff facts、
  `STF-001` identity、local status／eligibility／days／overlap／buffer 推導。
- 對 `union_db` 執行 mutation、seed、migration、repair 或建立測試資料；既有 DB 僅可做 GET UI 觀察。

## 5. Client／adapter 行為與 request budget

1. 每次 request 當下從既有 memory session client 讀取 bearer；無 token 時零 fetch，回 typed unauthenticated
   presentation。不得把 token 寫入 URL、localStorage、sessionStorage、cookie 或 fixture。
2. Initial roster：最多 1 個 `GET /api/v1/staff/summaries?page_size=200`。
3. `next_cursor`：只有操作者點擊 `staff.directory.next-page` 時才發 1 個 GET；每一 cursor 最多一次，
   不得 background poll、prefetch、auto retry 或 StrictMode double-fetch。
4. Drawer open／close、tab switch、filter unavailable、reload error presentation：0 個 GET；本包沒有
   staff detail endpoint，不得為 Drawer 自行加 endpoint。
5. 任一頁面 generation 切換或 component unmount 必須 abort 舊 request 並丟棄 stale response；不以舊頁資料
   覆蓋新頁，不以空陣列偽裝成功。
6. request timeout 沿用 shared transport；UI 顯示 typed timeout/network/error，不重試或假裝 empty。
7. 分頁資料只能 append 已驗證、未重複且 cursor forward 的 server items；不得顯示 loaded count 為全系統
   總數，也不得產生總筆數推估。

## 6. Tests、browser acceptance 與 anti-fake gates

### 6.1 Focused tests

- Client success：strict envelope、nullable `name/phone`、empty items、cursor query、互斥參數。
- Client negative：missing required、wrong primitive、null violation、extra field、duplicate id、repeated／
  non-forward cursor、401／403／422 typed error、503、timeout、abort。
- Adapter：只映射 `id/name/phone`；所有未提供欄位為 unavailable，不產生 business facts。
- Page：initial one-request budget、manual next page、loading/error/empty、Drawer no extra GET、tabs no GET、
  reload/session absence、stale response discard。
- Native controls：每個列出的 disabled control 皆無 fetch／alert／confirm／prompt；`MOCK_STAFF` 不在
  StaffPage dependency closure。
- Route：missing/invalid session fail closed；authorized GET 200；`staff_id + after_id` typed validation
  error；bounded cursor 與 retired `/api/v1/staff` 410 regression。

### 6.2 Real browser／existing DB only

取得 exact approval、啟動既有 FastAPI + Vite 並由人工完成真實帳密→TOTP 後：

1. 開啟 `http://127.0.0.1:5173/#staff`，記錄 Network 的 `GET /api/v1/staff/summaries` request、status、
   query 與 response 摘要；不得使用 dev token、mock response 或直接 DB query 偽造證據。
2. 將 response 中至少一筆去敏 `id/name/phone` 與 DOM Staff card 逐欄比對；null 欄位需看到 unavailable／—。
3. 若 response 有 `next_cursor`，人工點擊 `staff.directory.next-page`，確認只追加一個 cursor GET，且沒有
   duplicate card；沒有 cursor 時不宣稱 pagination 已測到第二頁。
4. 打開／關閉履歷 Drawer 與切換三 tabs，確認不發出非 GET；偏好／不可服務／主檔相關 controls 全部
   native disabled 且沒有假成功。
5. 登出或讓 memory session 過期後重新進入，確認頁面不帶 token fetch；401／auth state 明確呈現，不能把
   auth failure 當空名冊。F5 重新登入限制沿用 Phase 2C volatile session policy。
6. 全程只讀既有 DB：不得 INSERT／UPDATE／DELETE、seed、migration、repair、fixture 建立或 reset。

### 6.3 Static gates

- `npm run build`、focused Vitest、必要的 full React regression、`npm run lint`。
- strict UTF-8（無 BOM）、`git diff --check`、write-set audit、secret／PII scan。
- `rg` 證明 StaffPage dependency closure 無 `MOCK_STAFF`、`alert(`、`confirm(`、`prompt(`、`Date.now(`、
  非 GET method 或 hardcoded business facts；共同 `mockData.ts` 仍保留且不列入本包修改。
- 不以 build、component fixture、歷史 receipt、既有 DB final state 或「HTTP 200」單獨宣稱 real-data
  browser 完成。

## 7. Evidence 與缺口紀錄

本包的獨立 matrix 草案位於：
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-staff-query-page-slice/staff-query-evidence-matrix.md`。
它是驗收輸入／證據索引，不是 production 授權；implementation 後由 Integration Owner 追加實測 receipt，
不得以草案標記 PASS。

既有缺口沿用 canonical owner，不複製新 gap：

- Staff master、PII、證照、銀行 owner：`PROV-20260817-react-admin-phase3c-staff-master-owner-gap.md`。
- preference definition administration 與 end-pause：`PROV-20260817-react-admin-phase3b1-staff-remaining-controls-gap.md`。
- Preferences／Availability／Lifecycle mutation：`PROV-20260816-react-admin-phase3b1-staff-contract-hardening-selector-amendment.md`。

本包只新增一項 page-local backend gap disposition：`staff_summary_route_auth_and_conflict_error`，由
`api/routes/staff.py` 與 `tests/test_staff_summary_routes.py` 承接，不另立文件。

## 8. Gate table 與完成上限

| Gate | 未核准時 | 核准後最低證據 | 狀態規則 |
|---|---|---|---|
| G0 scope／write set | `BLOCKED` | exact approval、fresh dirty baseline、只改列定 paths | 不得擴張 |
| G1 contract matrix | `NOT_RUN` | Pydantic→Zod逐欄矩陣、auth／error／nullability | 缺欄明列 unavailable |
| G2 route auth／typed conflict | `NOT_RUN` | focused FastAPI route tests、0 DB mutation | 401／422 fail closed |
| G3 client／adapter | `NOT_RUN` | strict negative tests、cursor/stale/abort | raw payload不得入renderer |
| G4 page／control | `NOT_RUN` | request budget、0 fake mutation、UI slot tests | unavailable／disabled原位保留 |
| G5 static | `NOT_RUN` | build/lint/UTF-8/diff/secret/write-set | warnings不得隱藏 |
| G6 browser GET UI | `NOT_RUN` | 真TOTP、Network↔DOM、既有DB只GET | 沒有真browser不得PASS |

本包完成上限固定為 `query-real-data-validated`。任何 G1～G6 缺證據只能是 `blocked` 或
`in-progress`，不得升格為 mutation-ready、entry-readiness、cutover、replacement 或 retired。

## 9. DB gate（本包 0 DB change）

| DB gate | 狀態 | 證據／命令 |
|---|---|---|
| Scope gate | `PASS` | 2026-08-17 exact approval；production 只修改本包列定 query-only paths |
| Change inventory | `PASS` | 本包不含 schema／seed／backfill／destructive；write set 只有 query route hardening／React |
| Static release gate | `NOT_RUN` | 不適用；不改 schema |
| Descriptor gate | `NOT_RUN` | 不適用；不改 schema |
| Read-only plan gate | `NOT_RUN` | 不執行 DB plan；既有 DB 僅 browser GET |
| Engine verification gate | `NOT_RUN` | 不建立 disposable DB；query-only slice 不以 engine gate 阻塞 |
| Developer acceptance gate | `NOT_RUN` | 不操作 `union_db` |

依專案規範，必要 gate 尚有 `BLOCKED`／`NOT_RUN` 時結論固定為 `DB_CHANGE_NOT_READY`。這不表示 query
slice 不能在 exact approval 後以既有 DB 做唯讀 UI 驗收；它只禁止把本包說成 DB migration／mutation acceptance。

## 10. 2026-08-17 本地執行狀態

- Backend focused／bounded regression：`12 passed`。
- Staff frontend focused：5 files／`16 passed`；exact-file TypeScript 與 scoped oxlint 均 PASS。
- Staff production dependency closure：0 `MOCK_STAFF`、0 fake handler、0 direct fetch、0 non-GET。
- `npm run lint` exit 0；仍有不在本包 write set 的 `MasterLayout.tsx` 既有 2 warnings。
- 全量 React：450 passed／61 failed；失敗全在並行 Orders lane，Staff 5 files 全綠。
- 全量 build：被並行 Orders／Anomalies 型別漂移阻擋；exact Staff typecheck PASS。
- 真 TOTP browser／existing DB GET 尚未執行，G6 維持 `NOT_RUN`，本包保持 `in-progress`，不得升格
  `query-real-data-validated`。

本地證據位於
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-staff-query-page-slice/`。
