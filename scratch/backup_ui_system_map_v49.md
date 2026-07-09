# UI Functional Layer Sub-System Map (Version 49)

> **Scope**: `ui/` 所有介面與元件層  
> **Master Reference**: [`../system_map.yaml`](file:///c:/Users/chris/Desktop/project/Lobar_union---solo/system_map.yaml)

---

### 🏛️ UI 功能層模組全覽表

##### Module: AppShellUI
- Source: `ui/app.py`
- Type: ui_shell
- Description: Streamlit 側邊欄導覽殼層，動態分發載入 `ui/pages/` 專頁。

##### Module: DataBrowserUI
- Source: `ui/pages/01_data_browser.py`
- Type: ui_page
- Description: 原始資料庫表格瀏覽頁面與國定假日管理面板。

##### Module: OrderUI
- Source: `ui/pages/02_orders.py`
- Type: ui_page
- Description: 訂單與帳務管理系統殼層，包含 Tab1 總覽、Tab2 智慧配對與 Tab3 財務實收。

##### Module: CalendarUI
- Source: `ui/pages/03_calendar.py`
- Type: ui_page
- Description: 服務人員行事曆與檔期調控獨立頁面。

##### Module: EditOrderUI
- Source: `ui/pages/04_edit_order.py`
- Type: ui_page
- Description: 單筆訂單動態試算與資料維護頁面，配備 Formula Lock Guardrail 防呆機制。

##### Module: FormManagementUI (Current Focus)
- Source: `ui/pages/05_form_management.py`
- Type: ui_page
- State: `validated`
- Todo:
  - [x] 任務 1: B7, B185 連動契約生成/服務開始日期 (actual_start_date)
  - [x] 任務 2: P9 F25 連動服務總時數 total_hours
  - [x] 任務 3: P11 E28 連動服務時段 service_time
  - [x] 任務 4: 追溯訂單系統，更名 service_hours_per_day 為「每日服務時數」，區隔「總時數 (total_hours)」與「服務時段 (service_time)」
  - [x] 任務 5: B30 連結 F24 (天數), D30 連結 F25 (每日時數), F30 連結 B38 (自費總額)
  - [x] 任務 6: 稽核 E33 與 F1 連結，確認 beclass_records.gov_no 係無中生有，更正連動為 orders.case_no
  - [x] 任務 7: 查驗 beclass 與 服務人員 分頁，確認兩者皆完整包含銀行帳號與分行代號欄位
  - [x] 任務 8: P22 D36 匯款帳號連動服務人員 (月嫂) 銀行帳號 staff.staff_bank_account
  - [x] 任務 9: P24 C37 樓層費連動 orders.deposit_date (訂金入帳日)
  - [x] 任務 10: 稽核 P27~P33 欄位歸屬，確認 5 大欄位來自 clients (市府申請表)，更正二階歸屬分類
  - [x] 任務 11: P35 A48 服務時段連動至 E28 (service_time)
  - [x] 優先任務 3 (全量開載): 掃描資料庫來源表 100+ 個全量欄位填入 UI 二階選單，絕不漏載任何資料庫選項
  - [x] 需求 1 & 2 修復: E39 連動 orders.service_hours_per_day，D40, E40 成功連結至 clients.bank_code 與 bank_account
  - [x] 需求 4 升級 (100% 原生 Excel 換行與溢出重現): 讀取 cell.alignment.wrap_text 與整排合併儲存格，完美重現原檔排版
  - [x] Tab 3 移植 Tab 2 全套編輯、刪除二次確認對話框、取消隔離與硬碟儲存更新 (INV-UI-FORM-27)
  - [x] 實作 100% 全寬滿版契約預覽切換器 (INV-UI-FORM-28)
  - [x] PDF 純淨列印與顯式實心邊框繼承 (INV-UI-FORM-29)
  - [x] PDF 頁首頁尾 URL 去除與 @page 邊界消解 (INV-UI-FORM-30)
- Invariants:
  - `INV-UI-FORM-07`: 每個欄位配置 UUID4 全域唯一 field_id，刪除時採 ID 匹配過濾，嚴禁微秒時間戳碰撞導致 DuplicateKey 崩潰。
  - `INV-UI-FORM-11`: 移除 HTML 單據末尾備查蓋章處與簽章欄位。
  - `INV-UI-FORM-12`: 金額格式化實施精確單詞比對 (Exact Word Boundary Match Guardrail)，防止 `breastfeeding` 中含 `fee` 導致誤判為 0 元。
  - `INV-UI-FORM-13`: 採用獨立模板檔案目錄結構 (`db/templates/tpl_xx.json`)，實現錯誤隔離與單一模板獨立按需讀寫。
  - `INV-UI-FORM-14`: 綁定 DB 欄位支援按 SQL 資料表來源 (orders, clients, staff, beclass_records, global_stats) 兩階動態過濾選擇器。
  - `INV-UI-FORM-15`: 確保 case_no, client_name 等原生欄位直接歸屬至 SQL 原生資料表，直接讀取不經過二次無謂運算，提升最高 I/O 執行效率。
  - `INV-UI-FORM-16`: 支援 Excel 原生範本 (`.xlsx`) 之 `{P1}`, `{P2}` 變數標籤自動掃描解析器 (EPPP Protocol)。
  - `INV-UI-FORM-17`: 契約參數在 UI 端 100% 銜接兩階 SQL 資料表選擇器 (`orders`, `clients`, `staff`, `beclass_records`, `global_stats`)，實現 0 程式碼改動之動態綁定。
  - `INV-UI-FORM-18`: 支援雙軌輸出機制: 包含 1:1 CSS A4 影印級實時鏡像預覽 + Print-to-PDF，以及實體 `.xlsx` 填空檔案匯出下載。
  - `INV-UI-FORM-19`: Excel 長文字溢出不撐高公理 (Cell Overflow Protocol): 1:1 還原 Excel 長文字向右延伸疊加 (`white-space: nowrap`, `overflow: visible`)，固定每行列高，嚴禁換行拉高跑版。
  - `INV-UI-FORM-20`: Excel 顯式邊框與 PDF 列印去雜線公理: 僅繪製原檔顯式設定之邊框，空白單元格 100% 渲染為 `border: none;` 另存為 PDF 時自動清除多餘灰線。
  - `INV-UI-FORM-21`: 將 `所需表格.xlsx` 之 `客戶契約` 獨立抽出為 `db/templates/contracts/contract_client_copy.xlsx` 專屬極速範本檔，實現 0.01 秒讀載。
  - `INV-UI-FORM-22`: Excel 原生範本動態檔案監聽與即時鏡像刷新公理 (Real-time File Reload Protocol): 每次渲染強制解鎖檔控制代碼並以修改時間戳 os.path.getmtime 快取失效，確保使用者在外部用 Excel 修改 .xlsx 存檔後 UI 端 0.1 秒即時反映。
  - `INV-UI-FORM-23`: 動態底色清洗公理 (Dynamic Background Cleaning Protocol): Excel 範本保有原生黃底標註，鏡像渲染填入真實訂單資料時，自動將填空區黃底洗掉恢復為 transparent 乾淨紙本質感。
  - `INV-UI-FORM-24`: 指定儲存格自動折行公理 (Selective Cell Auto Line Wrap Protocol): 對 C39, C40 等長文字法規條款實施 white-space: normal; word-break: break-word; 自動換行，其餘普通欄位保持 nowrap 不拉高列高。
  - `INV-UI-FORM-25`: 全量資料庫欄位 100% 完整開載公理 (Full Schema Enrollment Protocol): 掃描 orders, clients, staff, beclass_records 100+ 個全量欄位填入 UI 二階選單，絕不漏載任何資料庫選項。
  - `INV-UI-FORM-26`: 原生 Excel 自動換行與溢出重現公理 (Native Excel Wrap Alignment Protocol): 100% 讀取實體 .xlsx 檔案之 alignment.wrap_text 標籤與整排合併儲存格設定，勾選 wrap_text=True 者自動折行，未勾選者 100% 保持文字原生溢出。
  - `INV-UI-FORM-27`: Tab 3 定型化契約範本全套生命週期管理公理 (EPPP Template Lifecycle Management Protocol): 套用 Tab 2 完整編輯、草稿隔離、二次刪除確認 modal 警示對話框、新增契約範本與單獨儲存更新 db/templates/contracts/*.json 功能。
  - `INV-UI-FORM-28`: 100% 全寬滿版契約預覽切換公理 (Full-Width Contract Canvas Switcher Protocol): 提供 5:5 左右對照維護模式與 100% 全寬滿版 A4 沉浸預覽模式無縫切換，解決 50% 寬度文字偏小問題。
  - `INV-UI-FORM-29`: PDF 純淨列印與顯式實心邊框繼承公理 (Pure PDF Print & Explicit Border Retention Protocol): 在 @media print 中隱藏所有 no-print UI 標頭標尾按鈕，配合 print-color-adjust: exact 確保 PDF 100% 完整保留 Excel 原生實心框線與 0 雜訊純淨單據。
  - `INV-UI-FORM-30`: PDF 頁首頁尾 URL 去除與 @page 邊界消解公理 (Print Header/Footer Suppression Protocol): 在 @media print CSS 導入 @page { margin: 0; } 阻斷瀏覽器列印引擎印出日期標題與 localhost:8501 網址頁尾。

---

### 📋 按鈕行為動作對照總表 (Behavioral Audit Matrix)

| 操作動作 | 按鈕名稱 | 作用記憶體 Scope | 寫入實體硬碟 `db/templates/tpl_xx.json` |
|---|---|---|---|
| 點擊編輯 | `[ ✏️ 編輯修改此模板 ]` | 產生獨立草稿 `edit_draft_tpl` | ❌ 絕不寫入 |
| 欄位順序調控 | `[ ⬆️ 上移 ]` / `[ ⬇️ 下移 ]` | 僅重排草稿欄位順序 | ❌ 絕不寫入 |
| 刪除單一欄位 | `[ 🗑️ 刪除欄位 ]` | 使用 `field_id` 從草稿中過濾 | ❌ 絕不寫入 |
| 點擊刪除模板 | `[ 🗑️ 刪除此表單模板 ]` | 開啟二次確認 Modal 警示對話框 | ❌ 絕不寫入 |
| 二次確定刪除 | `[ 💥 確定永久刪除 ]` | 從模板庫中剔除該模板 | ✅ **刪除對應 tpl_xx.json 檔** |
| 取消編輯 | `[ ✖️ 取消編輯 ]` | 徹底清空並丟棄 `edit_draft_tpl` 草稿 | ❌ **100% 丟棄，絕不寫入** |
| 確定更新 | `[ 💾 確定更新此模板 ]` | 將草稿覆蓋回主模板庫 | ✅ **單獨寫入該 tpl_xx.json 檔** |
