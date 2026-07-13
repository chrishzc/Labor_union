# UI Functional Layer Sub-System Map (Version 54.0)

> **Scope**: `ui/` 所有介面與元件層  
> **Master Reference**: [`../system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/system_map.yaml)

---

### 🏛️ UI 功能層模組全覽表

##### Module: AppShellUI
- Source: `ui/app.py`
- Type: ui_shell
- Description: Streamlit 側邊欄導覽殼層，動態分發載入 `ui/pages/` 專頁。

##### Module: DataBrowserUI
- Source: `ui/pages/01_data_browser.py`
- Type: ui_page
- State: `validated`
- Description: 原始資料庫表格瀏覽頁面與國定假日管理面板。支援 8 大資料表（包含銀行帳戶子表）欄位動態中文化對照與切換。
- Invariants:
  - `INV-UI-BROWSER-01`: 原始資料表格欄位必須支援透過對照表轉換為中文名稱 (含英文原鍵名或純中文)，未記錄欄位自動安全回退原鍵名。
- API Button Matrix:
  - `確認儲存假日` ➔ `POST /api/v1/holidays`
  - `確認刪除此假日` ➔ `DELETE /api/v1/holidays/{holiday_date}`

##### Module: OrderUI (Tab1~Tab3)
- Source: `ui/pages/02_orders.py`
- Type: ui_page
- State: `validated`
- Description: 訂單與帳務管理系統殼層，包含 Tab1 總覽、Tab2 智慧配對與 Tab3 財務實收。
- Invariants:
  - `INV-UI-01`: 所有費用與金額數字統一無條件四捨五入整數化呈現 (帶千分位)，無小數點。
  - `INV-UI-02`: 必須透過 safe_int() 轉換數值，防範 NaN, None, Inf 及空字串導致崩潰。
- API Button Matrix:
  - `1️⃣ 發送 訂單資訊-1 (粗篩)` ➔ `POST /api/v1/matches/{match_id}/send-info-1` (根據 staff.line_user_id 推播)
  - `2️⃣ 發送 訂單資訊-2 (精篩)` ➔ `POST /api/v1/matches/{match_id}/send-info-2` (根據 staff.line_user_id 推播)
  - `更新意願` ➔ `PUT /api/v1/matches/{match_id}/reply`
  - `🤝 3️⃣ 傳送履歷給客戶` ➔ `POST /api/v1/matches/{match_id}/send-resume`
  - `✍️ 4️⃣ 成立訂單並定案指派` ➔ `POST /api/v1/orders/{order_id}/assign-staff`
  - `🚨 確認取消此訂單` ➔ `PUT /api/v1/orders/{order_id}/status`
  - `更新財務記錄` ➔ `PUT /api/v1/payments/{order_id}`

##### Module: CalendarUI (完整四色月曆與排假精算專頁)
- Source: `ui/pages/03_calendar.py`
- Type: ui_page
- State: `validated`
- Description: 服務人員行事曆與檔期調控獨立頁面。包含兩階段時間操作選單、四色 HTML 月曆 (白/黃/紅/綠底)、7 天預留備用期動態渲染與國定假日單日獨立決策控制面板。
- Invariants:
  - `INV-CAL-01`: 必須在 HTML 月曆表格繪製前優先執行精算引擎，確保休假天數即時 100% 連動呈現。
  - `INV-CAL-02 (兩階段選單隔離)`: 「訂單匹配」模式僅展示黃底預排與 7 天備用期；「出勤天數精算」解鎖紅底工作日與綠底休假排假控制。
  - `INV-CAL-03 (四色月曆視覺公理)`: ⚪白底=無排班或解鎖區間; 🟡黃底=預排與 7 天備用期; 🔴紅底=服務工作日; 🟢綠底=自訂請假與國定假日放假。
  - `INV-CAL-04 (綠底休假與動態順延)`: 每增加 1 天綠底 🟢 休假，完工日 (`actual_end_date`) 自動向後動態順延 1 天。
  - `INV-CAL-05 (國定假日單日獨立決策)`: 支援國定假日單日個體勾選，放假者標示綠底 🟢 且完工日順延 1 天。
- API Button Matrix:
  - `💾 儲存放假與動態順延` ➔ `POST /api/v1/schedule/save`

##### Module: EditOrderUI
- Source: `ui/pages/04_edit_order.py`
- Type: ui_page
- State: `validated`
- Description: 單筆訂單 36 欄位動態試算與資料維護頁面，配備 Formula Lock Guardrail 防呆機制與全量持久化儲存。
- Invariants:
  - `INV-EDIT-01`: 修改輸入欄位時，費用與完工日必須即時連動試算，且金額統一無小數點 safe_int 呈現。
  - `INV-EDIT-03`: 所有由公式自動衍生之金額與時數欄位，預設必須為唯讀鎖定狀態。
  - `INV-EDIT-04`: 強制解鎖自動試算欄位時，必須顯性跳出警告告知公式連動失效風險。
  - `INV-EDIT-05`: 點擊儲存時必須同時調用 `update_order_full_details` 與 `update_payment_details` 完整寫入 orders, clients 與 payments 資料表。
- API Button Matrix:
  - `💾 確定儲存 36 欄位試算與變更結果` ➔ `PUT /api/v1/orders/{order_id}/full-details`

##### Module: FormManagementUI
- Source: `ui/pages/05_form_management.py`
- Type: ui_page
- State: `validated`
- Description: 表單與履歷問卷管理專頁，配備 EP Engine 契約引擎與雙軌輸出。
- Invariants:
  - `INV-UI-FORM-06`: 實施 Draft Buffer 編輯草稿隔離機制，點擊取消時 100% 丟棄記憶體草稿，嚴禁修改硬碟。
  - `INV-UI-FORM-09`: 刪除表單模板必須具備二次顯性確認視窗 (Delete Confirmation Modal Guardrail)，防範誤觸刪除。
  - `INV-UI-FORM-25`: 全量資料庫欄位 100% 完整開載公理。
  - `INV-UI-FORM-28`: 100% 全寬滿版契約預覽切換公理。
