# `staff_monthly_settlement_details` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/30_staff_monthly_settlement_details.sql`
- 父表關係：`settlement_id` → `staff_monthly_settlements.id`, `staff_payment_id` → `staff_payments.id`
- 子表關係：現況 Schema 有 `staff_transfer_allocations`；新流程不再建立逐明細匯款分配，該關係只供歷史資料讀取。
- **2026-08-02 後項人工裁決（優先於下方舊月結提案）**：業務不建立月結 Header／revision 或月結明細狀態機；本表只作既有 Schema／production caller 的歷史相容盤點，遷移完成前不刪除，新架構不得把它當成付款義務或核銷 SSOT。應付款清單直接由 `staff_payments` 與根事實查詢／匯出。
- **已被後項裁決覆寫的舊提案／現況模型**：本表曾被定義為月結 Header 的單一訂單／assignment 金額組成明細；下方逐欄表格只用來盤點 legacy schema 與 caller，不再代表目標付款模型，也不得新增寫入依賴。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 明細事實。 | 無。 | Settlement Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `settlement_id` | `BIGINT NOT NULL` | 所屬月結主表。 | 關聯鍵 | 不計算。 | 產生時綁定。 | `staff_monthly_settlements.id`。 | 必須對應。 | Settlement Service | 無 | 不變 | 無 | 已確認 |
| `staff_payment_id` | `BIGINT NOT NULL` | 所屬的案件應付主檔。 | 關聯鍵 | 不計算。 | 產生時綁定。 | `staff_payments.id`。 | 必須對應。 | Settlement Service | 無 | 不變 | 無 | 已確認 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 產生時綁定。 | `orders.case_no`。 | 必須對應。 | Settlement Service | 無 | 不變 | 無 | 已確認 |
| `assignment_id` | `BIGINT NOT NULL` | 本月結明細所對應的正式 assignment；同時是跨一般薪資與後續調整來源的共同查詢鍵。 | 驗證式關聯快照 | 現況複製 `staff_payments.assignment_id`；提案中的後續調整明細則取 `financial_adjustment_staff_allocations.assignment_id`。 | 本列恰好一個有效來源所指向的 assignment。 | `case_staff_assignments.id`。 | 保留；必須與 `staff_payment_id` 或 `financial_adjustment_staff_allocation_id` 所指 assignment 完全一致，不可由 caller 任意指定，也不具獨立業務權威。 | Settlement Service | 建立月結 revision | 建立後不變 | 可由來源關聯推導，但保留後可讓兩種互斥來源共用同一 assignment 查詢與 FK；若缺少一致性驗證會形成漂移。 | 已確認：保留驗證式共同 assignment 鍵 |
| `staff_id` | `INT NOT NULL` | 本月結明細所屬月嫂。 | 驗證式關聯投影／待移除 | 現況由月結 Header 傳入並與 assignment／staff payment 交叉驗證。 | `staff_monthly_settlements.staff_id` 與來源 assignment。 | `staff.id`。 | 長期考慮移除；移除前必須同時等於父月結、assignment 及來源義務的月嫂，不具獨立權威性。 | Settlement Service | 建立月結 revision | 建立後不變 | 重複保存父表與 assignment 可推導值；現況 writer 有一致性檢查，但沒有找到依賴本欄的實際 caller。 | 已確認：長期考慮移除 |
| `service_salary` | `DECIMAL(12, 2) NOT NULL` | 一般薪資快照。 | 歷史快照 | 從 `staff_payments` 複製。 | 月結當下抓取。 | 案件薪資。 | 無。 | Settlement Service | 無 | 定稿後凍結 | 無 | 已確認 |
| `legacy_subsidy_payable` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 舊制補助應付構成快照。 | 歷史相容快照／待移除 | 現況由建立月結 request 直接帶入；若大於 0，須搭配補助覆核狀態與備註。 | 現況 caller；但沒有可驗證的正式補助義務來源。 | 歷史非零資料的原始根事實目前不完整；新流程不得新增。 | 長期考慮移除。新流程固定為 0 並禁止 caller 輸入；既有非零資料僅供歷史唯讀。任何新補付金額必須走 `financial_adjustments` 及 assignment 分配。 | 新流程無寫入 Owner | 無新寫入 | 既有月結快照不改寫 | 現況 API request 可直接提供金額，沒有正式補助來源關聯，是高風險雙來源。 | 已確認：新流程固定 0，長期考慮移除 |
| `floor_fee_amount` | `DECIMAL(12, 2) NOT NULL` | 樓層費快照。 | 歷史快照 | 從 `staff_payments` 複製。 | 月結當下抓取。 | 案件樓層費。 | 無。 | Settlement Service | 無 | 定稿後凍結 | 無 | 已確認 |
| `adjustment_amount` | `DECIMAL(12, 2) NOT NULL` | 調整項快照。 | 歷史快照 | 從 `staff_payments` 複製。 | 月結當下抓取。 | 案件調整項。 | 無。 | Settlement Service | 無 | 定稿後凍結 | 無 | 已確認 |
| `payable_amount` | `DECIMAL(12, 2) NOT NULL` | 此訂單／assignment 在該月結 revision 的應付構成合計快照。 | 衍生計算／定稿快照 | `service_salary + legacy_subsidy_payable + floor_fee_amount + adjustment_amount`。 | 同列應付構成。 | assignment 工時、費率、樓層費、有效財務調整分配及合法舊制補助事實。 | 必須等於同列構成加總；整張月結 `total_payable` 再加總所有明細。本列只說明總額來源，不另維護銀行核銷餘額。 | Settlement Service | 月結 Preview／revision 重建 | 定稿後凍結 | 若把本列誤當獨立付款義務，會產生逐案件／逐元件 allocation 與不必要的狀態同步。 | 已確認：月結組成，不獨立核銷 |
| `legacy_subsidy_status` | `ENUM('not_applicable', 'confirmed', 'review_required') NOT NULL DEFAULT 'not_applicable'` | 舊制補助構成的覆核狀態。 | 歷史相容狀態／待移除 | 現況金額為 0 時強制 `not_applicable`；金額大於 0 且未符合確認條件時改為 `review_required`。 | 現況 caller 提供的狀態與 `review_note`。 | 舊制補助歷史快照。 | 長期考慮移除。新流程因 `legacy_subsidy_payable` 固定為 0，不再建立或推進本狀態；既有值只供歷史唯讀。 | 新流程無寫入 Owner | 無新寫入 | 既有月結快照不改寫 | 狀態只用來防守已停用且缺乏根事實的 caller 金額，沒有新流程業務用途。 | 已確認：歷史唯讀，長期考慮移除 |
| `review_required` | `BOOLEAN NOT NULL DEFAULT FALSE` | 月結明細是否需要人工覆核的彙總旗標。 | 歷史相容衍生投影／待移除 | 現況完全由 `legacy_subsidy_status='review_required'` 決定。 | `legacy_subsidy_status`。 | 舊制補助覆核結果。 | 長期考慮移除。新流程固定為 `FALSE` 且不再寫入；既有值只供歷史唯讀。本欄不具獨立權威性。 | 新流程無寫入 Owner | 無新寫入 | 既有月結快照不改寫 | 與 `legacy_subsidy_status` 一對一重複，Schema CHECK 強制兩者相同；舊制補助停用後沒有新用途。 | 已確認：歷史唯讀，長期考慮移除 |
| `review_note` | `VARCHAR(500) NULL` | 舊制補助構成的覆核說明。 | 歷史相容文字快照／待移除 | 現況由建立月結 request 帶入；補助金額大於 0 且缺少有效確認時參與覆核判定。 | 現況 caller 人工輸入。 | 舊制補助歷史覆核說明。 | 長期考慮移除。新流程不再寫入；既有內容只供歷史唯讀。未來人工財務更正的理由必須跟隨具事件 ID、操作者與時間的正式調整／沖銷事件保存。 | 新流程無寫入 Owner | 無新寫入 | 既有月結快照不改寫 | 無法知道由誰、何時核准；又與已停用的舊制補助狀態耦合。 | 已確認：歷史唯讀，長期考慮移除 |
| `created_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 本月結明細建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 明細建立事件。 | 沿用已確認技術時間規則：只供追查，不參與薪資或付款計算。 | DB／Settlement Service | 建立明細 | 建立後不變 | 無。 | 已確認：沿用技術建立時間規則 |

補充集合約束：一般薪資明細所屬訂單的 `orders.staff_payment_due_date` 月份必須等於父表 `settlement_month`；同一月嫂、同一訂單應付月份的所有有效 assignment／`staff_payments` 都必須納入同一 revision。後續 adjustment 明細則依下一個尚未 finalized 月份納入。兩者都不得由 caller 選擇性漏列。

現況結構缺口：本表目前要求 `staff_payment_id NOT NULL`，且 Service 禁止同一 `staff_payment` 進入另一張未取消月結。原 assignment 已完成付款後，後續 `financial_adjustment_staff_allocations` 因此無法作為下一月份獨立月結義務，不能靠重用原 `staff_payment_id` 或複製原薪資明細解決。

已確認調整方向：本表改為支援兩種互斥來源。一般薪資明細使用 `staff_payment_id`；已付月結之後才核准的調整明細使用 `financial_adjustment_staff_allocation_id`。兩者必須恰好一個有值，不得同時有值或同時為空。調整明細的服務薪資與樓層費為 0，只保存該調整分配金額，避免重複帶入原 assignment 薪資。

| 提案欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `financial_adjustment_staff_allocation_id` | 現況不存在；待建，建議 nullable FK → `financial_adjustment_staff_allocations.id` | 已付舊月結後，新調整進入下一個未 finalized 月結時的獨立來源。 | 條件式關聯鍵 | 不計算。 | 月結候選集合依新調整義務建立。 | `financial_adjustment_staff_allocations.id`。 | 與 `staff_payment_id` 必須 XOR。此欄有值時 `service_salary=0`、`legacy_subsidy_payable=0`、`floor_fee_amount=0`，`adjustment_amount` 取該分配的帶符號金額。 | Settlement Service | 後續調整進入下一個開放月結 | 月結 revision 建立後不變 | 若重用原 `staff_payment_id`，會把已付服務薪資與樓層費再次納入。 | 已確認採用 |
| `staff_payment_id`（約束修正） | 現況 `BIGINT NOT NULL`；提案改為 `BIGINT NULL` | 一般 assignment 基礎薪資月結來源。 | 條件式關聯鍵 | 不計算。 | 同 due month 的有效 `staff_payments`。 | `staff_payments.id`。 | 與 `financial_adjustment_staff_allocation_id` 必須 XOR；一般薪資明細不可同時帶後續調整來源。 | Settlement Service | 建立一般薪資明細 | 月結 revision 建立後不變 | 現況 NOT NULL 阻止後續調整成為獨立明細。 | 已確認採用 |
