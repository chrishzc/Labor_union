# `staff_payments` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`assignment_id` → `case_staff_assignments.id`；提案中的 `adjustment_amount` 由 `financial_adjustment_staff_allocations` 依 assignment 加總投影
- 子表關係：`staff_monthly_settlement_details`, `staff_payment_transactions`
- 已確認跨表裁決（2026-08-02 後項裁決覆寫舊月結提案）：本表為**單一訂單指派的應付金額 Projection**。應付總額 (`total_payable`) 來自 assignment-owned 工時、時薪、樓層費與共用調整分配。業務維持應付款清單／Excel 匯出，不建立人工月結、draft／finalized 狀態機或即時計算月結文件；同一月嫂同月多訂單只在查詢／匯出時按 `staff_id` 合併。現有 `staff_monthly_settlements` 相關表與 caller 只作歷史相容，遷移完成前不刪除，新架構不得再形成依賴。部分或不符出款只留在匯入／異常層，不得形成正式付款中間狀態。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 帳務事實。 | 無。 | Staff Payment Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `assignment_id` | `BIGINT NOT NULL` | 所屬的正式指派紀錄。 | 關聯鍵 | 不計算。 | 建立時帶入。 | `case_staff_assignments.id`。 | 必須有效對應。 | Staff Payment Service | 無 | 不變 | 無 | 已確認 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 建立時帶入。 | `orders.case_no`。 | 無。 | Staff Payment Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 月嫂 ID。 | 關聯鍵 | 不計算。 | 建立時帶入。 | `staff.id`。 | 無。 | Staff Payment Service | 無 | 不變 | 無 | 已確認 |
| `service_hours` | `DECIMAL(10, 2) NOT NULL DEFAULT 0.00` | 本 assignment 總工時投影。 | 衍生計算 | assignment-owned 正式服務日數 × `orders.service_hours_per_day`。 | `case_staff_assignments.actual_hours` 的同源正式服務日根事實。 | 有效 assignment-owned 正式服務日與訂單每日服務時數。 | 從根事實重算；不得 fallback 到 `planned_hours`、人工工時微調或 `orders.staff_id`。 | Assignment Payroll Projection | 正式服務日或每日服務時數變更 | 案件服務資料鎖成立後差額走 adjustment／reversal | 現況仍可能把快取或人工微調當來源。 | 已確認：只從 assignment 根事實計算 |
| `hourly_rate` | `DECIMAL(10, 2) NOT NULL DEFAULT 0.00` | 時薪。 | 衍生計算 | 從合約或主檔。 | `case_staff_assignments.hourly_rate`。 | 薪資設定。 | 同步自 `case_staff_assignments`。 | Schedule Sync | 無 | 結案凍結 | 無 | 已確認 |
| `service_salary` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 一般服務薪資。 | 衍生計算 | `hours * rate`。 | 系統計算。 | 工時與時薪。 | `service_hours * hourly_rate`。 | Payment Calculator | 工時變動 | 結算凍結 | 無 | 已確認 |
| `floor_fee_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 樓層費分攤金額。 | 衍生計算 | 依訂單分攤。 | `case_staff_assignments`。 | 訂單約定。 | 同步自指派紀錄。 | Payment Calculator | 訂單變更 | 結算凍結 | 無 | 已確認 |
| `adjustment_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 該 assignment 所有有效財務調整分配的摘要。 | 衍生投影 | 現況為手動輸入。 | 現況直接寫入本欄；提案改由 `financial_adjustment_staff_allocations` 加總。 | 核准的 `financial_adjustments` 與逐筆 assignment 分配。 | `SUM(financial_adjustment_staff_allocations.amount_delta)`，排除已取消的調整／分配；不得再由人員直接修改摘要。 | Financial Adjustment Service／Payment Calculator | 調整建立、取消、反向調整 | 帳務核銷前隨有效調整重投影；核銷後以反向調整保留歷史 | 現況把人工輸入的彙總結果當來源事實，無法追溯原因、共用調整 ID 或多月嫂分配。 | 已確認修正：改為共用調整分配投影 |
| `total_payable` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 應付總額。 | 衍生計算 | 薪資 + 樓層費 + 加減項。 | 系統加總。 | assignment 工時、時薪、樓層費，以及核准的財務調整分配。 | `service_salary + floor_fee_amount + adjustment_amount`；各構成均須追溯至第一層根事實。 | Payment Calculator | 任一構成或有效調整變動 | 未核銷時重算；已發生付款後以反向調整／新調整保留歷史 | 若 `adjustment_amount` 可直接輸入，本欄會把不可追溯的中間結果再次當計算來源。 | 已確認 |
| `amount_paid` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 單一 assignment 的相容性已付摘要；不具獨立核銷權威。 | 衍生相容投影／待移除 | 只有包含本義務的正式出款核銷使完整所選應付義務精確歸 0 時，才投影本列完整 `total_payable`；否則為 0。 | 不可變正式出款、reversal 與完整核銷結果。 | 原始銀行支出事實與本次完整應付義務集合。 | 長期考慮移除；不得保存部分正式已付。退匯／沖正使有效實付淨額不足時重投影為 0 並回到應付；不依賴月結 Header。 | Staff Remittance Reconciliation／Compatibility Projection | 完整核銷、退匯或反向更正 | 正式交易不可改寫；摘要可重建 | 欄名易被誤認為可人工累加的 assignment 銀行事實。 | 已確認：完整歸零才投影 |
| `due_date` | `DATE NULL` | 訂單層正式月嫂應付日的重複相容欄位；不得再作獨立權威來源。 | 衍生相容投影／待移除 | 暫存期間只能等於所屬 `orders.staff_payment_due_date`。 | 訂單層正式月嫂應付日。 | 訂單完成事實與客戶付款類型。 | 取消或實際服務日更正後沿用原訂單既定應付日，不自動改到下一個 15 日；原日期已過而新增／改變義務時進異常中心。長期移除前禁止銀行日期、View 或 `COALESCE` 覆寫。 | Staff Payment Compatibility Projection | 訂單應付日形成或合法更正 | 原應付日形成後不因取消任意改期 | 同一訂單多 assignment 重複保存相同日期；現況匯出又優先使用 View 日期。 | 已確認：沿用原訂單應付日 |
| `paid_at` | `DATE NULL` | 單一 assignment 的相容性付清日；不具獨立核銷權威。 | 衍生相容投影／待移除 | 只有完整應付義務精確核銷時，投影該次正式出款的最後實際日期；否則為空。 | 不可變正式銀行出款與完整核銷結果。 | 原始出款實際日期。 | 長期考慮移除；不得由下載、匯出、人工勾選或部分付款設定。 | Compatibility Projection | 完整核銷或 reversal | 正式交易歷史保留；投影可重建 | 容易被誤認為獨立付款事實。 | 已確認：只由完整核銷投影 |
| `payment_status` | `ENUM('pending', 'partially_paid', 'paid', 'cancelled', 'review_required') NOT NULL DEFAULT 'pending'` | 應付款清單的相容性狀態投影；不具獨立狀態機權威。 | 衍生相容投影／待移除 | `pending` 對外顯示「應付」；完整核銷且餘額精確為 0 才為 `paid`／「已完成」；退匯／沖正可回到應付。 | 有效應付義務與不可變正式出款淨額。 | assignment 薪資根事實、adjustments 與銀行出款事件。 | 新流程不產生 `partially_paid`；不足額、超付或金額不符一律 `review_required`／異常，不形成正式中間狀態。下載 Excel 不改變本投影。 | Staff Remittance Reconciliation／Compatibility Projection | 義務重算、完整核銷、退匯或 reversal | 正式交易不可改寫；投影可重建 | 現況仍允許部分付款且與月結 Header 形成雙狀態機。 | 已確認：應付／已完成／異常 |
| `notes` | `TEXT NULL` | Schema 預留的單一 assignment 應付摘要自由文字備註。 | 未使用預留欄位／待移除 | 不計算；現況建立時維持 `NULL`。 | 現況沒有 writer。`create_staff_payment()` 未寫入本欄，Staff Payments API 沒有本欄更新命令，Data Browser 對本表為唯讀；UI 的必填調整原因實際寫入舊 `staff_payment_transactions.notes`，不是本欄。 | 無已確認業務事件。 | 長期考慮移除；財務更正原因應跟隨不可變調整／沖銷事件保存，不應寫在可覆寫的應付摘要。 | 現況無 Owner | 無 | 無現況寫入 | 欄位存在但沒有業務入口；若未來直接啟用，會與正式財務事件原因形成雙來源。 | 已確認：長期考慮移除 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 本列建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 建立事件。 | 保留；只用於追查薪資投影建立時點，不參與工時、薪資、應付月份或付款狀態計算，也不能取代正式財務事件的稽核紀錄。 | DB／Staff Payment Service | 建立列 | 建立後不變 | 無。 | 已確認：保留技術建立時間 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 本列最後更新時間。 | 稽核／技術投影 | DB 於列更新時覆寫。 | 任一欄位更新。 | 最近一次資料列異動。 | 保留；可用於除錯、判斷薪資投影或快取的新鮮度，不參與薪資與付款計算，也不能取代具原因、內容與操作者的不可變稽核事件。 | DB | 任一列更新 | 持續覆寫 | 只能知道最後更新時間，不能說明改了什麼或為何修改。 | 已確認：保留技術更新時間 |
