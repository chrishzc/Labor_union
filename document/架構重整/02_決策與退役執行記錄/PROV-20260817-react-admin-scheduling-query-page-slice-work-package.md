---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-scheduling-query-page-slice
date: 2026-08-17
owner: Scheduling React Page Integration Owner
domain: Scheduling
subsystem: scheduling-current-query / staff-summary-selector
authority: PROV-20260817-react-admin-page-slice-migration-execution-decision
prerequisites: 已核准逐頁精簡遷移裁決；PROV-20260817-react-admin-staff-query-page-slice completed；不依賴 mutation Scenario、disposable DB、Phase 3B2 或 Holiday contract
approval_required: 核准此 exact React Scheduling Query Page-Slice Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-scheduling-query-page-slice/
completion_ceiling: query-real-data-validated
ui_execution_mode: browser-required
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: 任何SchedulingPage、相關API或共享transport drift都必須重新盤點後才可施工
---

# React Scheduling：逐頁精簡 query page-slice 工作包

> Activation：使用者已明確回覆「核准此 exact React Scheduling Query Page-Slice Work Package」。本包
> Staff Query產出並驗證可重用directory artifacts後，本包依序完成施工。

> Completion：backend 12、React focused 7、full React 517 tests與build通過；真Chrome staff summaries與
> current-calendar GET均200並進DOM，所有mutation控制維持disabled。狀態為`completed`。

## 1. 目的與邊界

本包只把既有 React `SchedulingPage` 的「服務人員排班甘特月曆／current calendar」改為真實唯讀資料。
它不是整個 Scheduling domain 的重整，也不是 Phase 3B action handler、Holiday、Leave/Substitution、
matching 或 Phase 5 entry cutover 的授權。

現有 React 畫面保留既有 tab、卡片、甘特表、legend、篩選、Drawer 位置與 CSS 視覺階層；資料來源改為：

1. `GET /api/v1/staff/summaries`：只取得去敏、cursor 分頁的服務人員摘要，供目前頁面選擇與 loaded-scope 篩選。
2. `GET /api/v1/scheduling/staff/{staff_id}/current-calendar`：以月份日期範圍取得 server-owned current
   Scheduling projection。

目前可確認的 live evidence：

- `api/schemas/scheduling_current.py` 已有 `extra="forbid"` 的 assignment/day/case-version/projection view。
- `subsystems/scheduling/current_projection_workflow.py` 是唯讀 query workflow；沒有 Apply、outbox 或 provider side effect。
- `infrastructure/mysql/scheduling_current_projection_repository.py` 只讀 current assignments、official schedule、buffer、
  waiting lock 與 staff unavailability facts。
- `ui/pages/03_calendar.py` 已使用上述 current-calendar client 顯示 server projection，但仍同時包含其他 mutation／preview workspaces。
- `ui_react/src/pages/SchedulingPage.tsx` 目前仍使用 `MOCK_STAFF`、`MOCK_ORDERS`、硬編日期與本地 business mutation，必須在本包範圍內移除其對 calendar tab 的假資料依賴。

既有 `PROV-20260817-react-admin-phase3b-q-h-scheduling-current-public-query-work-package.md` 與
`PROV-20260817-react-admin-phase3b-q-r-scheduling-current-query-react-work-package.md` 是本包的契約／盤點來源，
不得與本包平行施工。它們的 status、README、主計畫與 shared dependency matrix 不在本包 write set；由 Integration Owner
在後續索引同步時裁決 successor／superseded 關係。

## 2. 業務語意與 non-goals

### 2.1 本包要證明

- 同一已登入且 enabled 的內部使用者可選擇已載入服務人員與月份，看到 server current projection。
- 日期、assignment lifecycle、occupancy kind、case version 與 projection token 只顯示 server 回傳值。
- `official_workday`、`assignment_rest`、`assignment_buffer`、`waiting_deposit_service`、
  `waiting_deposit_buffer`、`staff_unavailability` 只作 server view 的顯示分類；UI 不重算日期、buffer、coverage、eligibility、薪資或可服務資格。
- 搜尋與 filter 明確標示 `loaded scope`；未載入的服務人員不能被計入總數或被推導為空閒。
- 既有資料庫只能用於 GET 的 UI 觀察；不得 seed、repair、migration、mutation 或建立測試資料。

### 2.2 明確排除

- 請假、代班、順延、實際開工、精算、國定假日新增／修改／刪除／加倍薪、訂單 matching、預約鎖定。
- `GET /api/v1/holidays`、orders summary、assignment-schedules、candidate pool 或任何未核准 projection。
- Leave/Substitution、Holiday、matching 的任何 preview/apply/receipt/re-query。
- DB schema、migration、seed、backfill、production data、worker、outbox、LINE、付款或外部 provider。
- Staff master CRUD、證照、銀行、履歷、偏好或 availability mutation；只使用 staff summary selector 所需三欄。

所有排班非 calendar tab 保留導覽位置，但內容只能呈現「此 page-slice 尚未開放／後端 typed contract 尚未提供」；
不得繼續 render 原本的 mock rows、假狀態或假成功。

## 3. Exact write set

### 3.1 Backend：僅必要的 local public-boundary hardening

以下檔案是允許修改的唯一 backend write set；不得修改 Domain、repository SQL、schema release 或 shared error handler：

- `api/routes/scheduling_current.py`：將 query auth 收斂至既有 enabled-principal `require_admin`；確認 range、correlation header、
  typed error 與 not-found／unavailable mapping。不得加入寫入或改變 projection 規則。
- `api/schemas/scheduling_current.py`：只有 live contract matrix 發現 required／nullable／extra
  漂移時才可在此做最小 public view 修正；不得新增 business-derived 欄位或 catch-all。
- `tests/test_scheduling_current_router.py`（新增或在現有專屬測試中補齊）。

`api/routes/staff.py`、`api/schemas/staff_summary.py`、`tests/test_staff_summary_routes.py`與
`ui_react/src/api/staff_directory/**`由Staff Query Page-Slice擁有，本包只讀重用且不得競寫。

`subsystems/scheduling/current_projection_workflow.py`、`infrastructure/mysql/scheduling_current_projection_repository.py`、
`domains/scheduling/current_projection.py` 僅作 read-only evidence。若必須修改它們才能使 query page 通過，停止本包並建立獨立
bounded successor，不得把 domain／SQL 重構藏在本包。

### 3.2 React bounded client／adapter／presentation

- `ui_react/src/api/scheduling/scheduling_current_schemas.ts`
- `ui_react/src/api/scheduling/scheduling_current_errors.ts`
- `ui_react/src/api/scheduling/scheduling_current_client.ts`
- `ui_react/src/adapters/scheduling/scheduling_current_adapter.ts`
- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/SchedulingPage.css`

若 Phase 3B1 的 `staff_directory` artifact 在本包施工前已完成並通過契約驗證，必須重用它，不能建立第二個 selector client。
`SchedulingPage` 不得 direct fetch、import `mockData` 或把 staff master 欄位複製到自己的 fixture。

### 3.3 Fixtures／focused tests／evidence

- `ui_react/src/tests/fixtures/scheduling/scheduling_current_contract_fixtures.ts`
- `ui_react/src/tests/scheduling_current_client.test.ts`
- `ui_react/src/tests/scheduling_current_adapter.test.ts`
- `ui_react/src/tests/scheduling_current_page.test.tsx`
- `ui_react/src/tests/scheduling_no_fake_mutation.test.tsx`
- `ui_react/src/tests/scheduling_request_budget.test.tsx`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-scheduling-query-page-slice/`

不得修改 `package.json`、`package-lock.json`、`transport.ts`、`runtime_decoder.ts`、Auth session owner、其他 React page、
shared README、main plan、dependency matrix 或既有 evidence。

## 4. Frozen query contract（執行前產出 final matrix）

### 4.1 Staff summary selector

`GET /api/v1/staff/summaries?page_size=20&after_id=<cursor>`：

- `page_size`：server bounded integer `1..200`；本頁固定初始 `20`，不得使用無界全量名冊。
- `after_id`：nullable positive cursor；`staff_id` 與 `after_id` 互斥。
- success item 只允許 `id: positive integer`、`name: string|null`、`phone: string|null`；
  `next_cursor: positive integer|null`。
- `phone` 不進 Scheduling render；不可將 phone、年資、區域、證照、技能、銀行或在職狀態補到 view model。
- duplicate id、非前進 cursor、unknown extra、invalid primitive、missing required field 必須 fail closed。

### 4.2 Current calendar projection

`GET /api/v1/scheduling/staff/{staff_id}/current-calendar?range_start=YYYY-MM-DD&range_end=YYYY-MM-DD`：

- `staff_id` positive integer；月份 range 由畫面導覽產生，必須 `range_end >= range_start`，且不得超過 server 62-day bound。
- success view 僅接受：`staff_id`、`range_start`、`range_end`、`evaluated_at`、`assignments`、`days`、`case_versions`、
  `projection_token`；nested DTO 全部 strict。
- `assignment` 的 `assignment_id/generation_id/scheduling_version/staff_id`、server lifecycle、assigned dates、
  `first_service_at/completion_at`、official service day count、actual hours 均只顯示 server facts。
- `day` 的 `calendar_date`、`available`、`entries[]` 只依 server view render；entry 的 occupancy kind、case number、assignment／lock／segment／
  unavailability identity 不可由前端重新計算。
- projection token 只作 lineage／測試證據，不可當作日期、狀態或 eligibility 的推導輸入。
- unknown extra、missing required、wrong primitive、invalid enum、duplicate day、range mismatch、invalid token 必須 fail closed。

### 4.3 Error and auth

401、403、404 `staff_not_found`、422 invalid range／parameter、409 data-integrity／occupancy conflict、503 storage unavailable、
500 internal 均必須落入現行 Global typed error envelope，含 correlation id；React 不得依中文 message 或 raw exception text 分支。
沒有 memory session token 時 client 必須零 fetch；session expiry 回到 shell login／明確 unavailable，不得用 mock 或 anonymous fallback。

## 5. UI mapping 與 stable IDs

### 5.1 Query-enabled slots

- `scheduling.page`：頁面 shell。
- `scheduling.tab.calendar`：唯一本包 real-data tab。
- `scheduling.calendar.staff-select`：staff summary selector，nullable name 顯示 `月嫂 #<id>`。
- `scheduling.calendar.year-select`、`scheduling.calendar.month-select`、`scheduling.calendar.previous-month`、
  `scheduling.calendar.next-month`、`scheduling.calendar.today`：只改變 query range，不改 Domain facts。
- `scheduling.calendar.search`、`scheduling.calendar.filter.all|active|waiting|leave`：只作用於已載入 projection，顯示 loaded scope。
- `scheduling.calendar.retry`：使用者明確觸發的同一個 GET retry；不得背景輪詢。
- `scheduling.calendar.row`、`scheduling.calendar.day`、`scheduling.calendar.assignment`：穩定 identity 由 server id/date 組合而來。

甘特表日期欄由 server `days` 陣列 render；不得固定 31 columns、固定 2026/08、固定今天 8/15、固定 staff／order bar、
固定 buffer 天數或以 start/end date 在前端算出 service range。

### 5.2 Unavailable／disabled slots

以下 stable controls 必須保留原位置但原生 `disabled`，並顯示「後端未開放／此 page-slice 不包含 mutation」：

- `scheduling.tab.leave_sub` 內 `scheduling.leave.apply`、代班／順延選擇與所有保存按鈕。
- `scheduling.tab.holidays` 內 `scheduling.holiday.create`、`toggle-rest`、`toggle-pay`、`delete`、`save`。
- `scheduling.tab.leave_inbox` 內 `scheduling.leave-inbox.accept`、`reject`。
- calendar 內 `scheduling.projection.order-select`、`scheduling.projection.clear`、`scheduling.projection.lock`、
  `scheduling.precision.open`、`scheduling.precision.save`、批次日期、新增／刪除休假與任何 Drawer Apply。

非 calendar tab 不得顯示原本 `MOCK_STAFF`／`MOCK_ORDERS`／local holidays／local leave records。可保留 card、table、Drawer slot，
但資料區必須是明確 unavailable，不得以空陣列冒充後端成功。

## 6. Request budget、狀態與失敗行為

### 6.1 Budget

| 操作 | 上限 | 規則 |
|---|---:|---|
| 初次進入 calendar | 1 staff summary GET + 最多 20 current-calendar GET | page size 固定 20；無 staff 時不發 current-calendar |
| staff summary 下一頁 | 1 staff summary GET + 最多 20 current-calendar GET | cursor 必須前進；不得重複已看過 cursor |
| 月份／年份切換 | 最多 20 current-calendar GET | abort 舊 generation；只對目前載入 staff 發送 |
| staff selection | 最多 1 current-calendar GET | 未選 staff 時不發 request |
| search／filter | 0 GET | 僅 loaded scope local filter |
| retry | 使用者每次明確點擊最多 1 個受影響 GET | 無自動重試、無 polling、無 StrictMode duplicate fetch |

每個 request 必須有 AbortSignal、明確 timeout、X-Correlation-ID 與 memory bearer；前端不得發出任何 POST／PUT／PATCH／DELETE。
可採最多 4 個並行 current-calendar request，但總數不得超過上述 budget；每列錯誤獨立呈現。

### 6.2 Exhaustive page state

頁面使用可判別 union，不以互相矛盾的 loading/error/loaded boolean 組合：

```text
idle
→ staff_loading
→ staff_ready | staff_empty | staff_error
→ calendar_loading
→ calendar_ready | calendar_empty | calendar_partial_error | calendar_error
```

每個 row 另有 `idle | loading | ready | empty | error | aborted`。月份／staff/page cursor 變更時遞增 generation，
abort 舊 request 並丟棄 stale response；stale response 不得覆蓋目前 selection。

- loading：顯示既有 table skeleton／載入提示，不顯示舊 mock。
- empty：明確顯示「目前範圍沒有 server projection」；不得以可接案、完全空閒或未排班推導。
- 401/403：交由 shell login／unavailable；不得 anonymous fetch。
- 404：顯示「找不到此服務人員／目前範圍」，不得自動選第一筆 staff。
- 409/422/503/timeout/network：顯示 typed code／可重試狀態與 correlation；不得清空成成功或補假資料。
- partial row error：保留成功列並在錯誤列顯示 unavailable/error；不得把全頁標成全部成功。

## 7. Anti-fake 與驗收門禁

### G0 Scope／baseline

- exact approval、最新 base/head、dirty paths、`SchedulingPage.tsx/.css` fresh baseline 已記錄。
- 本包是 SchedulingPage 唯一 presentation writer；舊 3B-Q-H/R 不得同批修改相同檔案。

### G1 Contract matrix

- 逐欄列出兩個 GET 的 Pydantic path、required/nullable、extra policy、HTTP status、typed error、redaction、UI slot 與 loaded-scope語意。
- 不得用 `dict[str, Any]`、catch-all、`.default()`、`z.record()`、`.passthrough()`、`z.any()`、`as any` 或 `unknown as` 繞過 drift。

### G2 Backend query

- route real TestClient／focused tests 覆蓋 auth、range、cursor、not-found、empty、typed unavailable、correlation 與 0 commit。
- 若需要 staff summary auth hardening，必須證明未改 query SQL、page limit 或 staff master exposure。
- 不得修改 DB、Domain、repository 或加入 hidden transaction。

### G3 Client／adapter

- success、missing required、wrong primitive、null violation、extra field、invalid enum、duplicate day／id、range mismatch、invalid token 負向測試全通過。
- adapter 只做 server view → presentation mapping；不得計算 service end、7-day buffer、coverage、eligibility、payroll、conflict 或 matching recommendation。

### G4 Presentation／request behavior

- loading／empty／error／auth／timeout／abort／stale／partial row／reload／deep-link 測試通過。
- 任意月份或 staff 變更都能證明舊 response 不會覆蓋新 selection；request count 不超過 budget。
- 所有 non-calendar controls native disabled；0 `alert()`／`confirm()`／`prompt()`／假成功。

### G5 Static and regression

- `npm run build`、`npm run lint`、focused Vitest 與既有 React full suite 通過。
- strict UTF-8、file header、`git diff --check`、secret／PII scan、write-set audit 通過。
- `rg` 證明 Scheduling production dependency closure 無 `MOCK_STAFF`、`MOCK_ORDERS`、固定正式樣本、`Date.now()` business identity、
  inline business arrays、non-GET 或 fake mutation。

### G6 Real browser query evidence

- 真實 FastAPI + Vite + TOTP session；Network 必須只看到 staff summary/current-calendar GET，DOM 顯示 server fixture／既有 DB 的可追溯 staff id、
  range、occupancy 與 projection token lineage。
- 以既有 DB 只能做 GET UI observation；若 server／登入／資料不可用，證據標為 `BLOCKED_REAL_BROWSER_EVIDENCE`，不得以 Happy DOM、HTTP 200、mock fixture 或舊 Streamlit screenshot 代替。
- 驗證 reload、deep-link `#scheduling`、月份切換、staff 分頁、empty/error 與 disabled mutation controls。

完成上限：只有 G0–G6 適用項目通過，才可標 `query-real-data-validated`；不得宣稱 mutation、entry cutover 或 Streamlit retirement 完成。

## 8. Required final evidence（執行時產出，不在本草案預先宣稱）

在指定 evidence directory 產出：

- `contract-field-matrix.md` 與 `contract-matrix-freeze-receipt.md`
- `candidate-change-inventory.md`
- `verification-receipt.md`
- `browser-smoke-receipt.md`
- `open-findings.md`

本次只建立獨立的 `page-slice-evidence-matrix-draft.md`；它不是 freeze receipt，也不是 implementation evidence。

## 9. DB gate

| Gate | Status | Evidence／reason |
|---|---|---|
| Scope gate | PASS | exact approval已取得；query-only page slice且0 DB |
| Change inventory | PASS | 只允許 API public boundary（若必要）與 React query presentation；不操作資料庫 |
| Static release gate | NOT_RUN | 無 schema／release 變更 |
| Descriptor gate | NOT_RUN | 無 owned-object 變更 |
| Read-only plan gate | NOT_RUN | 不適用；既有 DB 僅供 GET UI observation |
| Engine verification gate | NOT_RUN | 本包不建立新 DB、不跑 mutation；不得以 UI 觀察冒充 engine evidence |
| Developer acceptance gate | NOT_RUN | 不套用 migration、不修改既有 DB |

結論固定為 `DB_CHANGE_NOT_READY`；此結論不阻擋 query-only page-slice 的 API／UI 驗收，但不授權任何 DB／mutation 行為。

## 10. Rollback and successor routing

Query failure 時只把 `#scheduling` navigation 回到既有 Streamlit `/calendar` entry；不回滾 Domain data，也不以保留舊 URL 冒充 mutation rollback。
任何 leave、holiday、matching、actual-start、precision、provider、transaction、schema 或 production cutover 需求都必須建立獨立 successor Work Package。
