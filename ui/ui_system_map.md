# UI System Map

##### Module: AppShellUI
- Sub Map: ui_layer
- Type: ui_shell
- Source: ui/app.py
- Description: Streamlit 側邊欄導覽殼層，動態載入 ui/pages/ 頁面。
- Dependencies: [DataBrowserUI, OrderUI, CalendarUI, EditOrderUI, FormManagementUI]
- Observability: not_required

##### Module: DataBrowserUI
- Sub Map: ui_layer
- Type: ui_page
- State: `validated`
- Source: ui/pages/01_data_browser.py::show
- Description: 原始資料庫表格瀏覽頁面。提供 clients, staff, orders, beclass_records, matching_records, holidays 與 staff_bank_accounts 檢視，以及國定假日管理面板。
- Dependencies: [DbService]
- Invariants:
  - INV-UI-BROWSER-01: 原始資料表格欄位必須支援透過對照表轉換為中文名稱 (含英文原鍵名或純中文)，未記錄欄位自動安全回退原鍵名。
- Observability: not_required

##### Module: OrderUI
- Sub Map: ui_layer
- Type: ui_page
- Source: ui/pages/02_orders.py::_render_order_page_shell
- Description: Page 2 訂單與帳務管理頁的殼層；建立固定順序的五個 Tab，並將已載入資料分派至各自的 renderer。
- Dependencies: [OrderUI_Tab1_Overview, OrderUI_Tab2_Assign, LegacyPaymentUIFreeze, AccountsPayableExportUI, SubsidyReconciliationRegisterUI]
- Input:
  - orders_data: 已載入的訂單資料。
  - clients: 已載入的客戶資料。
  - staff_list: 已載入的服務人員資料。
- Output:
  - page2_tabs: 依序渲染的訂單總覽、配對、帳務總覽、應付帳款與核銷補助 Tab。
- Invariants:
  - INV-UI-01: 所有費用與金額數字統一無條件四捨五入整數化呈現 (帶千分位)，無小數點。
  - INV-UI-02: 必須透過 safe_int() 轉換數值，防範 NaN, None, Inf 及空字串導致的 ValueError 崩潰。
  - 必須固定建立五個 Tab，且依序分派 Tab1、Tab2、LegacyPaymentUIFreeze、AccountsPayableExportUI 與 SubsidyReconciliationRegisterUI。
  - 不得直接讀取資料庫或帳務 API；資料載入只屬於 Page2TabNavigation，帳務寫入只屬於 PaymentManagementUI。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "-q", "tests\\test_order_ui_shell_ownership.py"], "cwd": "project", "expect_exit": 0}
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Non Goals:
  - 不改動 Tab3、Tab4、Tab5 各自 renderer 的帳務或報表行為。
  - 不新增客戶收款或月嫂應付／轉帳操作。
- Observability: not_required

##### Module: OrderUI_Tab1_Overview
- Sub Map: ui_layer
- Type: ui_component
- Source: ui/pages/02_orders.py::_render_tab1_overview
- Description: Tab 1 總覽表格。完全對齊 36 個完整訂單欄位清單。
- Observability: not_required

##### Module: OrderUI_Tab2_Assign
- Sub Map: ui_layer
- Type: ui_component
- State: `validated`
- Source: ui/pages/02_orders.py::_render_tab2_assign
- Description: Tab 2 渲染函數 (案件與配對中心)。僅列出「洽談中」待配對案件，提供單筆案件控制面板、4 大智慧粗篩可選條件 (含香山區等 city/address 比對與 7 天預留備用期) 與 4 步智慧配對流程。
- Invariants:
  - INV-UI-ASSIGN-01: 媒合紀錄清單僅能顯示至少有一項發送紀錄 (sent_info_1_at/sent_info_2_at) 或意願已變更的有效紀錄。
  - INV-UI-ASSIGN-02: 選取月嫂檢視時嚴禁 speculative 預先建立 DB 紀錄，必須在點擊發送/變更動作時按需 (On-Demand) 建立。
- Observability: not_required

##### Module: OrderUI_Tab3_Finance
- Sub Map: ui_layer
- Type: ui_component
- Source: ui/pages/02_orders.py::_render_legacy_mixed_payment_overview
- Description: Tab 3 渲染函數。舊財務介面已停用，僅顯示新帳務介面建置中提示。
- Observability: not_required

##### Module: CalendarUI
- Sub Map: ui_layer
- Type: ui_page
- State: `validated`
- Source: ui/pages/03_calendar.py::show
- Description: 服務人員行事曆與檔期調控獨立頁面。包含兩階段時間操作選單 (1. 執行操作: 單純看行事曆/訂單匹配/出勤天數精算; 2. 訂單選擇)、四色 HTML 月曆 (白/黃/紅/綠底)、7 天預留備用期動態渲染、國定假日單日獨立決策控制面板，以及持久化寫入 staff_schedule 檔期表。
- Invariants:
  - INV-CAL-01: 必須在 HTML 月曆表格繪製前優先執行精算引擎，確保休假天數即時 100% 連動呈現。
  - INV-CAL-02 (兩階段選單隔離): 「訂單匹配」模式僅於行事曆展示黃底預排與 7 天預留備用期，不顯示單日排假與出勤精算面板；「出勤天數精算」模式僅適用於確定實際開工日 (actual_start_date) 案件，解鎖紅底工作日與綠底休假排假控制。
  - INV-CAL-03 (四色月曆視覺公理): ⚪白底=無排班或超出完工日解鎖區間; 🟡黃底=預排案件與完工日後 7 天預留備用期; 🔴紅底=確定服務工作日; 🟢綠底=自訂請假與國定假日放假。
  - INV-CAL-04 (綠底休假與動態順延): 每增加 1 天綠底 🟢 休假，後續紅底 🔴 工作日與服務結束日 (actual_end_date) 自動向後動態順延 1 天，確保實際服務天數 100% 足額達 N 天。
  - INV-CAL-05 (國定假日單日獨立決策): 支援連假期間針對每一個獨立國定假日進行單日個體勾選；選擇放假者在月曆標示為綠底 🟢 且完工日順延 1 天，選擇上班者計為紅底 🔴 正常工作日 (預設雙倍薪資)。
- Observability: not_required

##### Module: EditOrderUI
- Sub Map: ui_layer
- Type: ui_page
- State: `validated`
- Source: ui/pages/04_edit_order.py::show
- Description: 單筆訂單動態試算與資料維護頁面。採用 st.columns 與帶邊框 Container 打造實體訂單單據視覺，具備 Formula Lock Guardrail 防呆機制。
- Invariants:
  - INV-EDIT-01: 修改輸入欄位時，費用與完工日必須即時連動試算，且金額統一無小數點 safe_int 呈現。
  - INV-EDIT-03: 所有由公式自動衍生之金額與時數欄位，預設必須為唯讀鎖定狀態。
  - INV-EDIT-04: 強制解鎖自動試算欄位時，必須顯性跳出警告告知公式連動失效風險。
  - INV-EDIT-05: 點擊儲存時必須調用 update_order_full_details 寫入訂單與客戶主資料；帳務由新帳務介面獨立處理。
- Observability: not_required

##### Module: FormManagementUI
- Sub Map: ui_layer
- Type: ui_page
- State: `validated`
- Source: ui/pages/05_form_management.py::show
- Description: 表單與履歷問卷管理專頁。支援動態新建自訂表單沙盒、線上編輯修改既有模板欄位名稱、拖拉平移排序、二次確認刪除防呆、5:5側邊雙視窗實時預覽/PDF導出、SQL原生資料表歸屬分類選擇器、獨立JSON模板目錄、Excel長文字溢出不撐高列高、顯式邊框與PDF乾淨去雜線、全量資料庫欄位100%開載、100%全寬滿版預覽切換器，以及 Tab 3: Excel 變數代理制式定型化契約引擎 (EPPP Engine)。
- Invariants:
  - INV-UI-FORM-01: 支援手動新增自訂欄位，並提供單行文字、多行文字、數字、日期與綁定 DB 欄位 5 大資料型態。
  - INV-UI-FORM-06: 實施 Draft Buffer 編輯草稿隔離機制，點擊取消時 100% 丟棄記憶體草稿，嚴禁修改硬碟。
  - INV-UI-FORM-09: 刪除表單模板必須具備二次顯性確認視窗 (Delete Confirmation Modal Guardrail)，防範誤觸刪除。
  - INV-UI-FORM-16: 支援 Excel 原生範本 (.xlsx) 之 {P1}, {P2} 變數標籤自動掃描解析器 (EPPP Protocol)。
  - INV-UI-FORM-25: 全量資料庫欄位 100% 完整開載公理 (Full Schema Enrollment Protocol): 掃描 orders, clients, staff, beclass_records 100+ 個全量欄位填入 UI 二階選單。
  - INV-UI-FORM-28: 100% 全寬滿版契約預覽切換公理 (Full-Width Contract Canvas Switcher Protocol): 提供 5:5 左右對照維護模式與 100% 全寬滿版 A4 沉浸預覽模式無縫切換。
- Observability: not_required

##### Module: LegacyPaymentUIFreeze
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_render_tab3_finance
- Description: Page 2 第三分頁的帳務明細總覽；先呈現全部案件的可篩選帳務摘要，僅在展開案件時才讀取客戶與月嫂交易明細，取代已移除的 legacy payments 編輯器。
- Input:
  - orders_data: current order list
- Output:
  - payment_overview: filterable all-case payment summaries with on-demand ledger details
- Invariants:
  - 不得查詢或寫入 legacy payments。
  - 預設必須以客戶收款總覽與月嫂應付總覽兩張獨立表格顯示全部已有帳務的案件，並提供案件編號、訂單狀態與各自付款狀態篩選；兩張表不得交錯欄位。
  - 客戶表必須顯示訂金、第一期、第二期各自的應收、實收、應收日與實收日，以及合計；有退還補助款時一併顯示。
  - 月嫂表必須逐筆顯示服務時數、單價、服務薪資、樓層費、調整額、應付／實付／餘額與付款日期，並使用 staff_payments 的 amount_paid 與 due_date 欄位。
  - 使用者選擇特定案件後，自動取得並在展開區顯示客戶／月嫂交易明細；不得預先讀取其他案件明細。
  - 實收／實付與日期只能來自交易明細；人工補登交易時必填原因，不得直接覆寫摘要欄位。
  - 不得在此分頁重複實作待匯清單或匯出功能。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: LegacyPaymentEditFreeze
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/04_edit_order.py::safe_float,safe_int,safe_date,safe_optional_date,render_editor
- Description: 停止訂單編輯頁讀寫舊 payments；訂單資料與狀態仍可儲存，新帳務改由新帳務介面處理。
- Invariants:
  - 不得呼叫 get_table_data('payments') 或 update_payment_details。
  - 訂單主資料與狀態更新不得因停用舊帳務同步而中斷。
- Verification:
  - must_have_assertions
- Observability: not_required

##### Module: LegacyPaymentBrowserFreeze
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/01_data_browser.py::format_col_header
- Description: 移除資料瀏覽頁所有 legacy payments 選項、欄位標籤與不可達的虛擬帳號／唯讀分支，避免 Contract 後留下過時程式碼。
- Invariants:
  - 原始碼不得包含 legacy payments 表名、caregiver_fee、caregiver_paid_at 或舊帳務虛擬帳號分支。
  - table_options 僅能瀏覽目前仍由 db_service 支援的資料表。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; text=Path('ui/pages/01_data_browser.py').read_text(encoding='utf-8'); forbidden=('payments', 'caregiver_fee', 'caregiver_paid_at'); assert not any(value in text for value in forbidden); print('LEGACY PAYMENT BROWSER PRUNED')"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "LEGACY PAYMENT BROWSER PRUNED"}
- Observability: not_required

##### Module: Page2TabNavigation
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::show
- Dependencies: [OrderUI]
- Description: Page 2 的入口；只載入 orders、clients、staff 並處理初始化錯誤，將資料交給 OrderUI 殼層渲染。
- Output:
  - page2_entry: 完成初始化後交由 OrderUI 顯示的訂單頁。
- Invariants:
  - 不得出現 get_table_data('payments')、update_payment_details 或 legacy payments SQL。
  - show() 仍可載入訂單頁所需資料，且不會因查詢不存在的舊表失敗。
  - show() 不得直接建立 Tab 或直接呼叫任何 Tab renderer；必須只呼叫 _render_order_page_shell(orders_data, clients, staff_list)。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "-q", "tests\\test_order_ui_shell_ownership.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: PaymentManagementUI
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_payment_api_request,_render_client_payment_ledger,_render_staff_payment_ledger
- Description: 提供客戶收款與月嫂應付／轉帳兩個獨立操作區；所有帳務讀寫只經 FastAPI，退還補助金額暫不提供 UI 操作。
- Input:
  - api_request: path、method 與 JSON payload。
  - client_ledger: case_no 與單一客戶帳務／交易明細。
  - staff_ledger: case_no 與同案月嫂應付／交易明細清單。
- Output:
  - client_receipt_zone: 客戶應收／實收、交易明細與收款／沖回提交表單。
  - staff_payable_transfer_zone: 月嫂應付／實付、交易明細與轉帳／沖回提交表單。
- Invariants:
  - 客戶收款與月嫂應付／轉帳必須是獨立操作區與表單；任一區塊儲存時不得覆蓋、改寫或重建另一張帳務表。
  - 客戶區只可讀寫 /client-payments/*；提交時只傳送 case_no、stage、transaction_type、amount、occurred_at、external_reference 與 notes。
  - 月嫂區只可讀寫 /staff-payments/*；提交時只傳送 staff_payment_id、transaction_type、amount、occurred_at、external_reference 與 notes。
  - external_reference 與 notes 為兩區提交交易的必填追溯資料；不得直接覆寫帳務摘要欄位。
  - 不得改動 LegacyPaymentUIFreeze 的 _render_tab3_finance；不得影響既有 Tab4 AccountsPayableExportUI 與 Tab5 SubsidyReconciliationRegisterUI。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "-q", "tests\\test_payment_management_ui.py"], "cwd": "project", "expect_exit": 0}
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Non Goals:
  - 不新增退還補助款操作 UI。
  - 不清理或改寫 _render_legacy_mixed_payment_overview。
  - 不處理 ADAD v2→v3 遷移、approved hash 回填、helper Source binding 或 FinanceImportRawStagingSchema 跨分片依賴。
- Observability: not_required

##### Module: AccountsPayableExportUI
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_render_tab4_accounts_payable
- Description: Reconnect Page 2's fourth accounts-payable tab and fifth subsidy-reconciliation tab to their read-only FastAPI endpoints.
- Complexity: low
- Invariants:
  - The tab is read-only preparation and download; it must not mark staff or client payments as transferred, paid, refunded, or submitted.
  - The tab must be the fourth Page 2 tab, while the existing frozen third finance tab remains unchanged.
  - 顯示永豐銀行月嫂款與台新銀行退還補助款總額；不得顯示解約退款。
- Algorithm:
  - Read monthly preview and XLSX only through FinanceReportRouter; do not import AccountsPayableExport or db_service directly.
  - Read quarterly and annual reconciliation previews and downloads only through FinanceReportRouter; do not import the reconciliation service directly.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: SubsidyReconciliationRegisterUI
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_render_tab5_subsidy_reconciliation
- Description: Add Page 2's fifth tab, 核銷補助清冊, with quarterly and annual read-only previews and XLSX downloads.
- Complexity: low
- Invariants:
  - The tab must be the fifth Page 2 tab and must not alter the previous four tabs.
  - Provide separate quarterly and annual views, with downloads only and no data writes.
  - Do not render the subsidized-citizen lower section when it has no rows.
- Algorithm:
  - Read quarterly and annual previews and downloads only through FinanceReportRouter; do not import the reconciliation service directly.
- Verification:
  - command: {"argv": [".venv\\\\Scripts\\\\python.exe", "-m", "py_compile", "ui\\\\pages\\\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: FinanceAlertCenterUI
- Sub Map: ui_layer
- Type: ui_page
- State: `planned`
- Source: ui/pages/06_finance_alerts.py::show
- Dependencies: [FinanceAlertRouter]
- Description: 提供跨 CLIENT、RETURN、SUBSIDY、STAFF、COMMON 的財務警示中心，供人工檢視、認領與解除，不直接操作正式帳務。
- Complexity: medium
- Input:
  - filters: status、alert_code、source domain 與分頁
  - operator_action: operator reference、claim 或 resolve reason
- Output:
  - alert_center: 警示清單、row/batch 或正式來源、候選、expected/actual/difference 與事件歷程
- Invariants:
  - UI 只可透過 FinanceAlertRouter 讀取、claim、resolve；不得 import FinanceAlertWorkflowService、FinanceAlertDetectionService、FinanceAlertEventService、db_service 或直接執行 SQL。
  - 不提供建立 transaction、allocation、retransfer、reversal、修改應收／應付或強制對平的操作。
  - resolve 畫面必須明示「解除警示不等於完成核銷」，並要求非空原因。
  - candidate snapshot 只供人工判讀；不得用預設選項、列表第一筆或同額候選自動提交正式對象。
- Algorithm:
  - 以獨立 Streamlit 頁面載入警示清單及詳細事件歷程，依狀態與警示編號篩選。
  - 對選定警示呼叫 claim 或 resolve API，顯示 conflict 與 invalid transition，不在 UI 本地假設成功。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\06_finance_alerts.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: StaffContractExcelMirror
- Sub Map: ui_layer
- Type: ui_component
- State: `planned`
- Source: ui/pages/05_form_management.py::render_excel_contract_mirror
- Description: Register and render the copied staff-service contract workbook through the existing read-only Excel mirror.
- Complexity: low
- Invariants:
  - The staff contract must use db/templates/contracts/服務人員契約.xlsx and must not modify that workbook.
  - Contract template selection must render any registered .xlsx contract through the same mirror path.
  - Only fields available in the selected order may be filled; unmapped template cells remain unchanged.
- Algorithm:
  - Fetch selected staff-contract context from ContractContextRouter by case_no and assignment_id; do not assemble contract facts from db_service directly.
- Verification:
  - command: {"argv": [".venv\\\\Scripts\\\\python.exe", "-m", "py_compile", "ui\\\\pages\\\\05_form_management.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required
