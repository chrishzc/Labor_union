# UI 頁面分割規格與 Agent 執行清單

## 0. 文件狀態

- 狀態：Phase 1 規劃草案，等待人工 Checkpoint 1。
- 適用分支：`codex/split-ui-pages-small-tables`。
- 基準提交：`5e29179`。
- 目的：把大型 Streamlit page 拆成可獨立維護、獨立驗證、可由不同 Agent 依序施工的 page shell、tab renderer 與小型 table/component。
- 本文件不是施工授權。Checkpoint 1 通過、SSOT 更新並重新核發 Task 前，Agent 不得套用 `stash@{0}` 或修改 UI 實作。

## 1. 現況與問題

### 1.1 Page 2 訂單與帳務

`ui/pages/02_orders.py` 同時承載：

- Page 入口與資料載入。
- 固定五個 Tab 的殼層。
- Tab 1 訂單總覽。
- Tab 2 案件配對。
- Tab 3 帳務總覽與交易操作。
- Tab 4 應付帳款預覽／下載。
- Tab 5 核銷補助清冊預覽／下載。
- 日期、金額、HTTP 與帳務表格共用 helper。

SSOT 已將上述行為拆成多個逐函式 Source 節點，但 Source 仍集中在同一檔案，導致：

- 同一來源檔無法同時核發多個開放 Task。
- 修改單一 Tab 容易碰到其他已部署節點。
- AST 測試容易只檢查殼層文字，沒有檢查真正 renderer。

### 1.2 Page 5 表單管理

`ui/pages/05_form_management.py` 同時承載：

- Page 入口、資料載入與三個 Tab 的調度。
- 表單建立器。
- 模板庫管理。
- 契約管理與 Excel mirror。
- JSON 持久化、contract context、HTML／PDF／Excel rendering helper。

目前只有 `FormManagementUI::show` 與 `StaffContractExcelMirror::render_excel_contract_mirror` 有明確 Source 所有權，其餘 Tab 與 helper 尚未形成可獨立核發的架構節點。

## 2. 分割原則

1. 本次只做結構搬移與依賴顯式化，不改 UI 文案、欄位、API 路徑、payload、排序、下載格式或商業規則。
2. Page shell 只負責資料載入、建立 Tab、傳遞已載入 context 與呼叫 renderer。
3. 一個 Tab renderer 只屬於一個架構節點與一個 Source。
4. 小型 table/component 只有在符合下列任一條件時才獨立：
   - 有獨立輸入／輸出與讀寫邊界。
   - 可被兩處以上重用，符合 Rule of Two。
   - 有獨立的安全性規則，例如「唯讀、不得 POST」。
   - 可用單獨測試直接驗收。
5. 只被單一 Tab 使用、沒有獨立契約的微小格式化函式留在該 Tab，不為了縮短行數過度拆分。
6. 禁止 `from ... import *`；所有跨檔依賴使用顯式 import。
7. 禁止 circular import。子模組不得反向 import page shell。
8. 禁止在 wrapper 註解或無效字串中保留測試關鍵字來通過 AST 測試。
9. Streamlit widget key、session state key、Tab 標題及順序必須保持不變。
10. 舊入口的公開函式若需暫時相容，只能做一次 delegation，且簽章、位置參數語意、預設值與回傳值必須完全相容。

## 2.1 已發現問題與實際影響

### `_payment_api_request` 位置參數不相容

既有契約是 `(path, method="GET", payload=None)`；先前草稿改成
`(method="GET", path="", payload=None, json_body=None)`。

影響：

- 舊呼叫 `_payment_api_request("/x", "POST", payload)` 會把 `"/x"` 當成 method、`"POST"` 當成 path。
- 最終可能呼叫錯誤 URL／HTTP method，或在 wrapper 與 implementation 之間發生 `TypeError`。
- 帳務交易可能完全送不出去；更危險的是錯誤被 wrapper 吞掉後只呈現一般 UI 錯誤。
- 舊測試若只搜尋函式名稱或 payload 字串，不一定能抓到位置參數語意已經交換。

處理原則：保留既有簽章與位置參數語意；若要加入 `json_body`，必須另做經核准的介面變更，不能夾在搬檔中。

### `_finance_report_request` 遺失 `params`／`download`

既有契約是 `(path, params=None, download=False)`；先前草稿 wrapper 只接受 `path`。

影響：

- Tab 4 無法傳月份等 query params，可能讀到錯誤月份或 API 預設資料。
- Tab 4／5 無法要求 binary download，XLSX 可能被當 JSON 解析或下載功能直接失效。
- 預覽仍可能顯示，使問題只在使用者按下載時才暴露。

處理原則：完整保留 `params`、`download`、回傳 bytes 與錯誤語意，並以直接呼叫測試驗證。

### Form 子模組 wildcard import

先前草稿使用 `from ...shared import *`。

影響：

- 每個 Tab 實際依賴哪些 helper 無法從 import 看出，容易漏搬或誤用隱式 global。
- shared 新增名稱可能無意間改變 child module 行為。
- ADAD `deny_imports`、Source 所有權、依賴審查與 circular import 分析失準。
- 測試 monkeypatch 可能 patch 錯 module namespace，造成看似通過但 runtime 使用另一個物件。

處理原則：改用顯式 import；shared 的公開介面需列入節點契約。

### wrapper 註解造成 AST 測試假陽性

先前草稿把舊測試會搜尋的 API path、payload 或關鍵字放在 wrapper 註解中。

影響：

- 測試會因「文字存在」而通過，即使真正 child renderer 已漏掉 API 呼叫、欄位或 guardrail。
- CI 顯示綠燈，但使用者操作時才發現功能消失。
- Agent 會把假通過當成可提交證據，污染後續 Task 與 Checkpoint 判斷。

處理原則：行為／AST 測試必須直接讀真正 implementation module；shell 只驗 delegation 與相容簽章。禁止用註解、死碼或常數字串滿足 assertion。

### Tab 3 節點重疊

目前 `OrderUI_Tab3_Finance` 綁定未使用的 legacy placeholder，
`LegacyPaymentUIFreeze` 才綁定實際 `_render_tab3_finance`。

影響：

- 節點名稱與實際畫面所有權相反，Agent 可能修改錯函式。
- Task、Source lock、dirty cascade 與 verification 可能落在未被 shell 呼叫的 placeholder。
- 真正 Tab 3 發生回歸時，錯誤節點的測試仍可能通過。

處理原則：退役 placeholder，讓 `OrderUI_Tab3_Finance` 成為實際 Tab 3 renderer 的唯一節點；舊節點只保留遷移紀錄，不再核發實作 Task。

## 3. 目標檔案結構

```text
ui/pages/
├── 02_orders.py
├── order/
│   ├── __init__.py
│   ├── shared.py
│   ├── editor.py
│   ├── tab1_overview.py
│   ├── tab2_assign.py
│   ├── tab3_finance.py
│   ├── tab4_accounts_payable.py
│   └── tab5_subsidy_reconciliation.py
├── 05_form_management.py
└── form_management/
    ├── __init__.py
    ├── shared.py
    ├── tab1_form_builder.py
    ├── tab2_template_library.py
    └── tab3_contract_management.py
```

若 `shared.py` 在規劃時需要承載多個不同責任，應進一步拆成具名模組，例如 `contract_context.py`、`template_repository.py`、`rendering.py`；不得形成第二個大型 page。

### 3.1 移除獨立 Page 4

本節的「Page 4」指 `ui/pages/04_edit_order.py` 的獨立側欄頁面，不是 Page 2 的第 4 個「應付帳款」Tab。

現況：

- `ui/app.py` 掃描 `ui/pages/*.py`；模組同時提供 `title` 與 `show()` 就會出現在側欄。
- `04_edit_order.py::show()` 只重複載入訂單、顯示簡化版訂單選單，再呼叫 `render_editor()`。
- Page 2 Tab 1 已提供狀態篩選、搜尋、完整訂單選單，並呼叫同一個 `render_editor()`。

目標：

- 移除 Page 4 的 `title`、`show()`、重複 `get_order_details()` 與 `guardrail_order_picker`。
- 將 `render_editor()`、必要 constants 與 helper 搬到 `ui/pages/order/editor.py`。
- Page 2 Tab 1 成為訂單編輯的唯一 UI 入口。
- `EditOrderUI` 從獨立 `ui_page` 改成 Page 2 使用的 `ui_component`。
- `AppShellUI` 移除對 `EditOrderUI` 的直接依賴；依賴路徑改為
  `AppShellUI → OrderUI → OrderUI_Tab1_Overview → EditOrderUI`。
- 更新 `EditOrderDerivedDateHelpers`、`LegacyPaymentEditFreeze` 的 Source。
- 最終刪除 `ui/pages/04_edit_order.py`；不得留下仍具 `title + show` 的相容 shim。

必須保留：

- `render_editor()` 的 38 欄位試算與公式鎖定。
- assignment synchronization preview／apply。
- 完整 assignment plan、排班移除確認、applied_by 與 blocking reason。
- `key_prefix + case_no` 的 widget/session-state 隔離。
- Page 2 Tab 1 的篩選、搜尋與選取後單次委派。

不可隨 Page 4 一起移除：

- Page 2 的第 4 個「應付帳款」Tab。
- `render_editor()` 中的同步安全門檻。
- `payments_raw=[]` 所暴露的 legacy 實收欄位問題；該問題不是 Page 4 專屬，若要清理必須另立節點與 Task。

## 4. Page 2 契約

### 4.1 `02_orders.py` shell

- 保留 Streamlit page title 與 `show()` 入口。
- `show()` 只載入 orders、clients、staff，處理初始化錯誤後委派 page shell。
- page shell 固定建立五個 Tab，順序不得改變：
  1. 訂單資訊總覽
  2. 案件與配對中心
  3. 帳務總覽
  4. 應付帳款
  5. 核銷補助清冊
- 每個 renderer 恰好呼叫一次。
- `ui/app.py` 只註冊 `02_orders.py`，不得把 `order/` 子模組當成獨立 page。

### 4.2 Order shared

- 數值／日期 helper 保留既有回傳與例外語意。
- `_payment_api_request` 相容簽章固定為：
  `(_path_, method="GET", payload=None)`，不得交換 path 與 method 的位置參數語意。
- `_finance_report_request` 相容簽章固定為：
  `(path, params=None, download=False)`，不得遺失 query params 或 binary download。
- HTTP helper 不得直接寫入 Streamlit session state。
- 若共用檔由多個 SSOT 節點擁有，必須使用互斥的逐函式 Source 綁定；禁止多節點整檔綁定。

### 4.3 Tab 1

- 保留全部訂單的狀態篩選、搜尋、單一下拉選單與 EditOrderUI 委派。
- 身分資格只讀取 `clients.identity_status`。
- 不得新增 DB 寫入或帳務 API 呼叫。

### 4.4 Tab 2

- 僅處理「洽談中」案件與既有配對流程。
- 不得在選取月嫂時預先建立資料；只允許在明確動作發生時寫入。
- 保留既有 callback、widget key、篩選條件與 DB 呼叫時機。

### 4.5 Tab 3

- 客戶收款與月嫂應付維持兩張獨立表格及兩個操作區。
- 明細維持按案件 lazy load，不得預讀所有案件交易。
- 人工補登交易必須保留 external reference 與 notes。
- 不得查詢或寫入 legacy `payments`。
- 必須先釐清 `OrderUI_Tab3_Finance` placeholder 與 `LegacyPaymentUIFreeze` 真正 renderer 的命名／退役策略，避免兩個節點聲稱擁有 Tab 3。

### 4.6 Tab 4

- 僅透過 FinanceReportRouter 讀取月度預覽與 XLSX。
- 保留 `params` 與 `download`。
- 完全唯讀；不得 POST，不得標記 transferred、paid、refunded 或 submitted。

### 4.7 Tab 5

- 僅透過 FinanceReportRouter 讀取季度／年度預覽與 XLSX。
- 空資料時不顯示不適用的下半部區塊。
- 完全唯讀；不得 POST 或修改核銷狀態。

## 5. Page 5 契約

### 5.1 `05_form_management.py` shell

- 保留 page title、`show()`、資料載入、scope／order 選擇與 global stats。
- 固定建立三個 Tab，順序不得改變。
- shell 與 child renderer 只能有一層 `with tab:`；不得雙重進入相同 tab context。
- 三個 renderer 恰好呼叫一次。
- `ui/app.py` 只註冊 `05_form_management.py`。

### 5.2 Form shared

- 公開 helper 必須列出顯式 import/export contract。
- JSON template CRUD、contract context、HTML rendering、Excel mirror 不得透過 wildcard import 洩漏全域名稱。
- Draft Buffer 取消時不得落盤。
- template delete 仍需二次確認。
- `identity_status` 仍為唯讀資料來源。

### 5.3 Tab 1 表單建立器

- 保留欄位新增、移動、資料型態、DB 欄位綁定、即時預覽及取消草稿行為。
- 傳入的 helper 必須實際使用；禁止參數存在但改讀隱式 global。

### 5.4 Tab 2 模板庫

- 保留模板載入、儲存、刪除、排序與預覽。
- 二次刪除確認與取消不落盤必須可獨立測試。

### 5.5 Tab 3 契約管理

- 保留 Excel `{P1}`、`{P2}` 掃描、contract context、A4 預覽與下載。
- `StaffContractExcelMirror` 維持唯讀，不得修改原始 workbook。
- case／assignment context 只從既有 Router 取得，不得在 UI 自行拼接 DB 真相。

## 6. Agent 原子任務順序

每項任務都必須是新核發的 Task；舊的 approved Task 不可重用。

| 順序 | 原子節點／任務 | 允許範圍 | 完成門檻 |
|---|---|---|---|
| A0 | UI SSOT 規劃 | `ui/ui_system_map.md` 與編譯 IR | CP-1 核准、Source 無歧義 |
| P4-1 | EditOrder core 搬移 | `order/editor.py` 與必要直接測試 | 編輯／同步契約完整保留 |
| P4-2 | Page 2 Tab 1 接線 | Tab 1 import／delegation 與必要測試 | Tab 1 仍可編輯且只委派一次 |
| P4-3 | 移除獨立 Page 4 | `04_edit_order.py`、AppShell 導覽與必要測試 | 側欄無 Page 4、Page 2 正常 |
| A1 | Order shared | `order/shared.py` 與必要直接測試 | 簽章相容、helper 測試通過 |
| A2 | Order Tab 1 | `order/tab1_overview.py` 與必要測試 | 真實 renderer 測試通過 |
| A3 | Order Tab 2 | `order/tab2_assign.py` 與必要測試 | callback／寫入時機不變 |
| A4 | Order Tab 3 | `order/tab3_finance.py` 與必要測試 | client/staff 邊界與 payload 不變 |
| A5 | Order Tab 4 | `order/tab4_accounts_payable.py` 與必要測試 | params/download 保留且無 POST |
| A6 | Order Tab 5 | `order/tab5_subsidy_reconciliation.py` 與必要測試 | 季／年下載保留且無 POST |
| A7 | Order shell | `02_orders.py` 與 wiring/AppTest | 五 Tab 固定且各委派一次 |
| B1 | Form shared | `form_management/shared.py` 與必要測試 | 無 wildcard/circular import |
| B2 | Form Tab 1 | `tab1_form_builder.py` 與必要測試 | Draft Buffer 與欄位操作不變 |
| B3 | Form Tab 2 | `tab2_template_library.py` 與必要測試 | CRUD／二次刪除不變 |
| B4 | Form Tab 3 | `tab3_contract_management.py` 與必要測試 | context／preview／download 不變 |
| B5 | Form shell | `05_form_management.py` 與 wiring/AppTest | 三 Tab 固定且各委派一次 |
| C1 | 整合驗證 | 原則上唯讀 | 全部檢查通過，失敗只回報 |

任務執行規則：

- P4-1 至 P4-3 必須依序執行；A1 至 A7 必須依序執行；B1 至 B5 必須依序執行。
- P4-1 應在 A2（Order Tab 1）之前完成，避免 Tab 1 繼續依賴數字 page module。
- Order 與 Form 在 Source lock 不衝突且 CP-1 已核准後可由不同 Agent 平行執行。
- 同一序列中不得同時修改 shell 與 child renderer。
- 每個 Agent 只能讀自己的 Task 快照；缺少 Task 或 Task stale 必須停止。
- 發現需要改 API、payload、DB schema、欄位或商業規則時，立即提出 Schema Update Request。

## 7. 每個 Agent 的必要檢查

### 7.1 開工前

- [ ] 確認目前分支為 `codex/split-ui-pages-small-tables`。
- [ ] 確認工作區沒有不屬於自己 Task 的變更。
- [ ] 讀取 `.agents/tasks/<node>.task.json`，確認 status 為 assigned／in_progress。
- [ ] 確認 Task 的 Source 與實際目標檔一致。
- [ ] 確認沒有同 Source 的 active lock。
- [ ] 不直接套用整包 `stash@{0}`。

### 7.2 實作期間

- [ ] 只搬移自己節點的函式與必要 import。
- [ ] 不改公開簽章、widget key、session state key、API path 或 payload。
- [ ] 不使用 wildcard import。
- [ ] 不讓 child import shell。
- [ ] 不用註解、死碼或字串滿足 AST assertion。
- [ ] 不順手格式化或清理其他 Tab。

### 7.3 節點驗收

- [ ] 新模組與既有 page entry 均可 import。
- [ ] 目標檔與 shell 均通過 `py_compile`。
- [ ] 原有行為測試改為直接檢查真正 implementation module。
- [ ] shell 測試只驗 wiring、delegation、順序與相容簽章。
- [ ] 空資料與最小非空資料皆無 Streamlit exception。
- [ ] renderer 產生自己的專屬 heading 或 widget，禁止空殼通過。
- [ ] widget key 唯一，rerun 後 session state 不漂移。
- [ ] `check_invariants.py` 與 `verify_implementation.py` 通過後才 submit。

## 8. 整合驗證矩陣

### 8.1 ADAD／架構

- `.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\compile_map.py`
- `.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\check_source_binding.py`
- `.venv\Scripts\python.exe .agents\skills\adad-workflow\scripts\check_domain_boundary.py`
- 每個被改節點執行 `read_context.py`，確認 Source、state、dependencies 與 verification。

### 8.2 Import／compile

- `importlib.import_module("ui.pages.02_orders")`
- `importlib.import_module("ui.pages.05_form_management")`
- 逐一 import 所有 `order.*` 與 `form_management.*` 子模組。
- 對兩個 shell 與所有子模組執行 `py_compile`。
- 驗證 `ui/app.py` 不會把子目錄註冊為額外 page。

### 8.3 Order UI

- 既有 focused baseline：
  - `test_order_ui_shell_ownership.py`
  - `test_payment_management_ui.py`
  - `test_order_overview_ui.py`
  - `test_order_assign_identity_status_ui.py`
- 新增五 Tab AppTest：空資料、最小非空資料、五個標題／renderer 均存在。
- `_payment_api_request`：path、method、payload 與錯誤語意。
- `_finance_report_request`：params、download、bytes 與錯誤語意。
- Tab 3：client／staff payload、lazy load、交易原因。
- Tab 4／5：唯讀、無 POST、下載參數完整。
- AppShell discovery 不包含「訂單動態試算與維護」，但仍包含 Page 2。
- Page 2 Tab 1 仍能載入並單次委派 `order/editor.py::render_editor`。
- `test_edit_order_synchronization_ui.py` 必須改為讀取新 Source，不得硬編舊 `04_edit_order.py`。

### 8.4 Form UI

- `test_form_management_identity_status_ui.py`
- 三 Tab AppTest：空資料與單一案件。
- 每個 Tab 的專屬 heading／widget。
- 表單欄位新增、移動、取消草稿不落盤。
- 模板 save/load/delete 與二次確認。
- contract context、HTML／A4 預覽、Excel mirror、下載。
- session state key 與 rerun。

### 8.5 回歸順序

1. 節點 focused tests。
2. Order 或 Form 的相關 UI tests。
3. 全部 UI tests。
4. 全專案 pytest；若 Windows cache／basetemp 權限失敗，依專案規範使用新的可寫 `--basetemp` 與 `-p no:cacheprovider` 重試。

## 9. 已知禁止事項與停止條件

- 先前 `stash@{0}` 只可作為差異參考，不可整包套回後宣稱完成。
- 草稿中的 `_payment_api_request` 交換了位置參數語意，必須拒絕。
- 草稿中的 `_finance_report_request` 遺失 `params`／`download`，必須拒絕。
- 草稿中的 Form wildcard import 必須拒絕。
- 只用 wrapper 註解讓舊 AST 測試通過，必須拒絕。
- 新增 Source 沒有 SSOT 節點、Source 重複綁定或 Task stale 時立即停止。
- 測試沒有可靠 exit code時不得宣稱 verified。
- 任一行為、欄位、API 或商業契約需要改動時立即停止並提出 Schema Update Request。
- 禁止直接刪除 `04_edit_order.py` 後才修 Page 2；必須先搬 editor、驗證 Tab 1，再移除 page entry。
- 禁止把「移除 Page 4」誤解成刪除 Page 2 的第 4 個應付帳款 Tab。

## 10. Checkpoint 1 審查項目

人工核准前需確認：

- [ ] 接受本文件的「只搬結構、不改行為」範圍。
- [ ] 決定 Tab 3 placeholder `OrderUI_Tab3_Finance` 的保留／退役策略。
- [ ] 核准新增 Form 三個 Tab 節點與必要 helper 節點。
- [ ] 核准既有 deployed／validated 節點的 Source 搬移與 dirty cascade。
- [ ] 核准 Order 與 Form 可在不同 Source lock 下平行施工。
- [ ] 核准每個節點重新產生 Task，不沿用舊 approved Task。
- [ ] 核准移除獨立 Page 4，並採完整分割方案：editor 搬到非 page 子模組後刪除 `04_edit_order.py`。

Checkpoint 1 通過後，Planning Agent 才能更新 `ui/ui_system_map.md`、編譯 IR、執行 cascade、核發第一批原子 Task。
