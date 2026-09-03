# `government_subsidy_allocations` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`06_政府補助與申請`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/80_government_subsidy_transactions.sql`
- 父表關係：`transaction_id` → `government_subsidy_transactions.id`, `claim_item_id` → `subsidy_claim_batch_items.id`
- 子表關係：無
- 已確認跨表裁決：本表為政府撥款的**分配矩陣 (M:N Allocation)**。解決「一筆大額的政府撥款」如何精準攤提到「批次內的各個單一訂單明細」的問題。它是批次主表上的 `paid_amount` 的唯一計算來源。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 分配事實。 | 無。 | Allocation Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `transaction_id` | `BIGINT NOT NULL` | 所屬的政府撥款。 | 關聯鍵 | 不計算。 | 分配演算產生。 | `government_subsidy_transactions.id`。 | 必須對應。 | Allocation Service | 無 | 不變 | 無 | 已確認 |
| `claim_batch_id` | `BIGINT NOT NULL` | 所屬批次。 | 關聯鍵 | 不計算。 | 分配演算產生。 | `subsidy_claim_batches.id`。 | 必須與 transaction 的批次一致。 | Allocation Service | 無 | 不變 | 無 | 已確認 |
| `claim_item_id` | `BIGINT NOT NULL` | 分配給的具體明細。 | 關聯鍵 | 不計算。 | 分配演算產生。 | `subsidy_claim_batch_items.id`。 | 必須對應。 | Allocation Service | 無 | 不變 | 無 | 已確認 |
| `allocation_type` | `ENUM(...) NOT NULL DEFAULT 'receipt'` | 分配方向 (正常分配/沖銷)。 | 來源事實 | 不計算。 | 分配邏輯。 | 款項方向。 | 無。 | Allocation Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `allocated_amount` | `DECIMAL(18, 2) NOT NULL` | 切分給該明細的金額。 | 衍生計算 | 演算法切分。 | 系統演算。 | transaction 餘額。 | `SUM(allocated_amount)` 必須等於 transaction 的總額。 | Allocation Service | 無 | 審核後凍結 | 無 | 已確認 |
| `reversal_of_allocation_id` | `BIGINT NULL` | 沖銷的對象。 | 關聯鍵 | 不計算。 | 沖銷操作帶入。 | 本表 `id`。 | 沖銷時必填。 | Allocation Service | 無 | 寫入後凍結 | 無 | 已確認 |
