# `staff_transfer_allocations` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成；確認為不必要的逐明細匯款分配
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/50_staff_transfer_allocations.sql`
- 父表關係：現況 `transfer_id` → `staff_actual_transfers.id`, `settlement_detail_id` → `staff_monthly_settlement_details.id`
- 子表關係：無
- 已確認跨表裁決：**整張表標記為新流程停寫、歷史相容唯讀、長期考慮移除**。月嫂的正式付款義務已由 `staff_monthly_settlements` Header 完整表達，`staff_monthly_settlement_details` 只說明金額組成；因此不需要再把銀行匯款 M:N 分配回訂單、assignment 或薪資元件。本表不得再作為 `staff_monthly_settlements.total_paid` 或 `staff_payments.amount_paid` 的權威來源，也不新增任何欄位。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 歷史相容鍵 | 不計算。 | DB 自增。 | 舊流程分配列。 | 新流程不再建立。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 本表整體無獨立業務必要性。 | 長期考慮移除 |
| `transfer_id` | `BIGINT NOT NULL` | 舊流程對應的實際銀行轉帳事件。 | 歷史相容關聯 | 不計算。 | 舊分配流程。 | `staff_actual_transfers.id`。 | 新流程直接以 transfer 的 `settlement_id` 核對月結 Header，不再建立本列。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 重複月結 Header 已有的轉帳歸屬。 | 長期考慮移除 |
| `settlement_detail_id` | `BIGINT NOT NULL` | 舊流程回配的案件應付明細。 | 歷史相容關聯 | 不計算。 | 舊分配流程。 | `staff_monthly_settlement_details.id`。 | 新流程不把銀行匯款回配至明細。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 把金額組成誤建模成獨立銀行義務。 | 長期考慮移除 |
| `allocated_amount` | `DECIMAL(12, 2) NOT NULL` | 舊流程逐明細分配金額。 | 歷史相容事實 | 舊核銷 Preview 產生。 | 舊分配流程。 | 舊正式轉帳與明細。 | 不參與新流程計算；新流程只驗證同次成功出款淨額等於月結 `total_payable`。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與月結總額核銷重複，增加差異同步風險。 | 長期考慮移除 |
| `component_type` | `ENUM(...) NOT NULL DEFAULT 'unknown'` | 舊流程的薪資元件分類。 | 歷史相容分類 | 舊分配演算產生。 | 舊分配流程。 | 月結明細構成。 | 新流程由月結明細直接呈現構成，不在匯款層重複分類。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 重複明細已有資訊。 | 長期考慮移除 |
| `allocation_method` | `ENUM('explicit', 'inferred') NOT NULL` | 舊流程的分配方式。 | 歷史相容狀態 | 舊演算法標記。 | 舊分配流程。 | 舊操作事實。 | 新流程不執行逐明細分配。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 新流程沒有對應業務動作。 | 長期考慮移除 |
| `review_status` | `ENUM(...) NOT NULL DEFAULT 'review_required'` | 舊流程的分配覆核狀態。 | 歷史相容狀態 | 舊人工覆核。 | 舊分配流程。 | 舊審核事實。 | 新流程不產生待覆核的推斷分配。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 新流程沒有對應業務動作。 | 長期考慮移除 |
| `reversal_of_allocation_id` | `BIGINT NULL` | 舊逐明細分配的反向關聯。 | 歷史相容關聯 | 舊沖銷分配指向原 allocation。 | 舊分配沖銷流程。 | `staff_transfer_allocations.id`。 | 新流程不建立 allocation 或其沖銷鏈；正式退匯／沖銷只使用 `staff_actual_transfers.reversal_of_transfer_id`。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與已確認移除的逐明細分配模型綁定。 | 長期考慮移除 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 舊分配列建立時間。 | 歷史相容技術時間 | DB 建立時寫入。 | DB 時鐘。 | 舊分配建立事件。 | 本表停寫；既有值只供歷史追查。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 隨整表退出新流程。 | 長期考慮移除 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 舊分配列最後更新時間。 | 歷史相容技術投影 | DB 於列更新時覆寫。 | 舊分配列更新。 | 舊流程最近異動。 | 本表停寫；既有值只供歷史追查。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 隨整表退出新流程。 | 長期考慮移除 |
