# `subsidy_claim_batch_items` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`06_政府補助與申請`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/70_subsidy_claim_batches.sql`
- 父表關係：`batch_id` → `subsidy_claim_batches.id`, `assignment_id` → `case_staff_assignments.id`
- 子表關係：`government_subsidy_allocations`
- 已確認跨表裁決：本表為補助申請批次內的「逐案件服務指派明細 (Detail)」。記錄每個特定案子申請了多少時數與補助金額，並快取政府針對該案最終核准與實際撥付的金額。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 申請項目事實。 | 無。 | Subsidy Claim Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `batch_id` | `BIGINT NOT NULL` | 所屬批次。 | 關聯鍵 | 不計算。 | 建立時綁定。 | `subsidy_claim_batches.id`。 | 必須對應有效批次。 | Subsidy Claim Service | 無 | 不變 | 無 | 已確認 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 建立時綁定。 | `orders.case_no`。 | 無。 | Subsidy Claim Service | 無 | 不變 | 無 | 已確認 |
| `assignment_id` | `BIGINT NOT NULL` | 所屬的服務指派。 | 關聯鍵 | 不計算。 | 建立時綁定。 | `case_staff_assignments.id`。 | 無。 | Subsidy Claim Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 月嫂。 | 關聯鍵 | 不計算。 | 建立時綁定。 | `staff.id`。 | 無。 | Subsidy Claim Service | 無 | 不變 | 無 | 已確認 |
| `claimed_hours` | `DECIMAL(10, 2) NOT NULL DEFAULT 0.00` | 申請時數。 | 來源事實 | 從排班或工時表複製。 | 建立時擷取。 | `actual_hours`。 | 無。 | Subsidy Claim Service | 無 | 送件後凍結 | 無 | 已確認 |
| `unit_price` | `DECIMAL(10, 2) NOT NULL DEFAULT 0.00` | 補助單價。 | 來源事實 | 依據當期政府規定。 | 建立時設定。 | 政策費率。 | 無。 | Subsidy Claim Service | 無 | 送件後凍結 | 無 | 已確認 |
| `requested_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 申請金額。 | 衍生計算 | `claimed_hours * unit_price`。 | 系統計算。 | 上述兩者。 | 建立批次時凍結，不受核准或撥款覆寫。 | Subsidy Claim Service | 無 | 送件後凍結 | 無 | 已確認 |
| `approved_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 實際核准金額。 | 來源事實 | 公文匯入。 | 手動或系統匯入。 | 政府公文。 | 無。 | Subsidy Claim Service | 無 | 核准後凍結 | 無 | 已確認 |
