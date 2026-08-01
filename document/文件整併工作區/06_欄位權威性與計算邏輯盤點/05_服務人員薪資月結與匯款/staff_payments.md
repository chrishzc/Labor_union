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
- 已確認跨表裁決：本表為**單一訂單指派的應付金額 Projection**。應付總額 (`total_payable`) 來自工時、時薪、樓層費與共用調整分配，並作為月結明細的來源；真正的付款義務與核銷狀態只存在於整張 `staff_monthly_settlements`。本表不再要求逐 assignment 銀行分配。部分或不符出款只留在匯入／異常層，不得形成正式付款中間狀態。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 帳務事實。 | 無。 | Staff Payment Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `assignment_id` | `BIGINT NOT NULL` | 所屬的正式指派紀錄。 | 關聯鍵 | 不計算。 | 建立時帶入。 | `case_staff_assignments.id`。 | 必須有效對應。 | Staff Payment Service | 無 | 不變 | 無 | 已確認 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 建立時帶入。 | `orders.case_no`。 | 無。 | Staff Payment Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 月嫂 ID。 | 關聯鍵 | 不計算。 | 建立時帶入。 | `staff.id`。 | 無。 | Staff Payment Service | 無 | 不變 | 無 | 已確認 |
| `service_hours` | `DECIMAL(10, 2) NOT NULL DEFAULT 0.00` | 總工時。 | 衍生計算 | 排班表加總。 | `case_staff_assignments.actual_hours`。 | 排班與微調。 | 同步自 `case_staff_assignments`。 | Schedule Sync | 工時微調 | 結案凍結 | 無 | 已確認 |
| `hourly_rate` | `DECIMAL(10, 2) NOT NULL DEFAULT 0.00` | 時薪。 | 衍生計算 | 從合約或主檔。 | `case_staff_assignments.hourly_rate`。 | 薪資設定。 | 同步自 `case_staff_assignments`。 | Schedule Sync | 無 | 結案凍結 | 無 | 已確認 |
| `service_salary` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 一般服務薪資。 | 衍生計算 | `hours * rate`。 | 系統計算。 | 工時與時薪。 | `service_hours * hourly_rate`。 | Payment Calculator | 工時變動 | 結算凍結 | 無 | 已確認 |
| `floor_fee_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 樓層費分攤金額。 | 衍生計算 | 依訂單分攤。 | `case_staff_assignments`。 | 訂單約定。 | 同步自指派紀錄。 | Payment Calculator | 訂單變更 | 結算凍結 | 無 | 已確認 |
| `adjustment_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 該 assignment 所有有效財務調整分配的摘要。 | 衍生投影 | 現況為手動輸入。 | 現況直接寫入本欄；提案改由 `financial_adjustment_staff_allocations` 加總。 | 核准的 `financial_adjustments` 與逐筆 assignment 分配。 | `SUM(financial_adjustment_staff_allocations.amount_delta)`，排除已取消的調整／分配；不得再由人員直接修改摘要。 | Financial Adjustment Service／Payment Calculator | 調整建立、取消、反向調整 | 帳務核銷前隨有效調整重投影；核銷後以反向調整保留歷史 | 現況把人工輸入的彙總結果當來源事實，無法追溯原因、共用調整 ID 或多月嫂分配。 | 已確認修正：改為共用調整分配投影 |
| `total_payable` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 應付總額。 | 衍生計算 | 薪資 + 樓層費 + 加減項。 | 系統加總。 | assignment 工時、時薪、樓層費，以及核准的財務調整分配。 | `service_salary + floor_fee_amount + adjustment_amount`；各構成均須追溯至第一層根事實。 | Payment Calculator | 任一構成或有效調整變動 | 未核銷時重算；已發生付款後以反向調整／新調整保留歷史 | 若 `adjustment_amount` 可直接輸入，本欄會把不可追溯的中間結果再次當計算來源。 | 已確認 |
| `amount_paid` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 單一 assignment 的相容性已付摘要；不具獨立核銷權威。 | 衍生相容投影／待移除 | 若本筆 `staff_payment` 已被納入的有效月結 revision 為 `paid`，則投影為該月結明細的 `payable_amount`；否則為 0。 | `staff_monthly_settlement_details` 與父表 `staff_monthly_settlements.status`。 | assignment 應付根事實、月結組成與整月正式出款。 | 長期考慮移除；移除前禁止從 `staff_transfer_allocations` 或人工分配推算，只能由父月結是否完整付清決定。 | Compatibility Projection | 月結完整核銷或反向更正 Apply | 正式交易與 paid 月結不可改寫；投影可重建 | 欄名容易讓 caller 誤認每筆 assignment 都有獨立銀行付款；現況 allocation 來源與新月結模型衝突。 | 已確認：長期考慮移除 |
| `due_date` | `DATE NULL` | 訂單層正式月嫂應付日的重複相容欄位；不得再作獨立權威來源。 | 衍生相容投影／待移除 | 暫存期間只能等於所屬 `orders.staff_payment_due_date`。 | 訂單層正式月嫂應付日。 | 訂單完成事實與客戶付款類型。 | 長期考慮移除；基本薪資月份直接讀訂單 SSOT。移除前禁止 caller、銀行日期或 View 各自覆寫，且不得使用 `COALESCE` 形成優先級。 | Staff Payment Compatibility Projection | 訂單應付日形成或合法更正 | 月結 finalized 後不得回寫既有快照 | 同一訂單多 assignment 重複保存相同日期；現況匯出又優先使用 View 日期，形成三套來源。 | 已確認：長期考慮移除 |
| `paid_at` | `DATE NULL` | 單一 assignment 的相容性付清日；不具獨立核銷權威。 | 衍生相容投影／待移除 | 若所屬有效月結為 `paid`，取該月結完成原子核銷的最後實際出款日；否則為空。 | 父月結的完整核銷結果。 | 所選原始出款實際日期與月結 Header。 | 長期考慮移除；移除前不得由 assignment 級交易或 allocation 各自判斷，只能由父月結完整核銷日投影。 | Compatibility Projection | 月結完整核銷 Apply | 正式交易歷史保留；投影可重建 | 逐 assignment 保存相同月結付款日屬重複資料，容易被誤認為獨立付款事實。 | 已確認：長期考慮移除 |
| `payment_status` | `ENUM('pending', 'partially_paid', 'paid', 'cancelled', 'review_required') NOT NULL DEFAULT 'pending'` | 單一 assignment 的相容性付款狀態；不具獨立狀態機權威。 | 衍生相容投影／待移除 | 現況依 assignment 級付款狀況推進。 | 現況 Service；新流程改由有效月結明細及父月結狀態投影。 | assignment 是否進入有效月結，以及 `staff_monthly_settlements.status`。 | 長期考慮移除；移除前只能反映父月結狀態，不得獨立推進。父月結 `paid` 才投影 `paid`；新流程不產生 assignment 級 `partially_paid`。 | Compatibility Projection | 月結建立、狀態變更或取消 | 正式 paid 月結不可改寫；投影可重建 | 現況具有自己的 `partially_paid` 與狀態推進，會與月結 Header 形成雙狀態機。 | 已確認：長期考慮移除 |
| `notes` | `TEXT NULL` | Schema 預留的單一 assignment 應付摘要自由文字備註。 | 未使用預留欄位／待移除 | 不計算；現況建立時維持 `NULL`。 | 現況沒有 writer。`create_staff_payment()` 未寫入本欄，Staff Payments API 沒有本欄更新命令，Data Browser 對本表為唯讀；UI 的必填調整原因實際寫入舊 `staff_payment_transactions.notes`，不是本欄。 | 無已確認業務事件。 | 長期考慮移除；財務更正原因應跟隨不可變調整／沖銷事件保存，不應寫在可覆寫的應付摘要。 | 現況無 Owner | 無 | 無現況寫入 | 欄位存在但沒有業務入口；若未來直接啟用，會與正式財務事件原因形成雙來源。 | 已確認：長期考慮移除 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 本列建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 建立事件。 | 保留；只用於追查薪資投影建立時點，不參與工時、薪資、月結月份或付款狀態計算，也不能取代正式財務事件的稽核紀錄。 | DB／Staff Payment Service | 建立列 | 建立後不變 | 無。 | 已確認：保留技術建立時間 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 本列最後更新時間。 | 稽核／技術投影 | DB 於列更新時覆寫。 | 任一欄位更新。 | 最近一次資料列異動。 | 保留；可用於除錯、判斷薪資投影或快取的新鮮度，不參與薪資與付款計算，也不能取代具原因、內容與操作者的不可變稽核事件。 | DB | 任一列更新 | 持續覆寫 | 只能知道最後更新時間，不能說明改了什麼或為何修改。 | 已確認：保留技術更新時間 |
