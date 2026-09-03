# `government_subsidy_transactions` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`06_政府補助與申請`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/80_government_subsidy_transactions.sql`
- 父表關係：`claim_batch_id` → `subsidy_claim_batches.id`, `finance_import_row_id` → `finance_import_rows.id` (財務匯入)
- 子表關係：`government_subsidy_allocations`
- 已確認跨表裁決：本表為**已唯一匹配正式申請批次的政府補助銀行事件 (SSOT)**。所有的撥款與退匯事件都在此，並與 `finance_import_rows` 財務流水連動，確保款項來源可追溯。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 撥款事件。 | 無。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `claim_batch_id` | `BIGINT NOT NULL` | 所匹配的申請批次。 | 關聯鍵 | 不計算。 | 財務對帳邏輯。 | `subsidy_claim_batches.id`。 | 必須匹配有效批次。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `finance_import_row_id` | `BIGINT NOT NULL` | 對應的財務匯入原始流水。 | 關聯鍵 | 不計算。 | 財務對帳。 | `finance_import_rows.id`。 | 保證 1:1 唯一 (防重複入帳)。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `transaction_type` | `ENUM('receipt', 'reversal') NOT NULL` | 交易方向 (撥款/沖銷)。 | 來源事實 | 不計算。 | 對帳邏輯。 | 金流方向。 | 無。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `transaction_status` | `ENUM(...) NOT NULL DEFAULT 'succeeded'` | 交易狀態。 | 狀態欄位 | 不計算。 | 對帳邏輯。 | 實際過帳。 | 只有 `succeeded` 才參與 allocation。 | Subsidy Transaction Service | 沖銷時 | 終態凍結 | 無 | 已確認 |
| `amount` | `DECIMAL(18, 2) NOT NULL` | 撥款金額。 | 來源事實 | 不計算。 | 財務流水。 | 入帳總額。 | 無。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 數值 |
| `occurred_at` | `DATE NULL` | 實際銀行入帳日。 | 來源事實 | 不計算。 | 財務流水。 | 日期。 | 無。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `external_reference` | `VARCHAR(191) NOT NULL` | 銀行流水憑證號。 | 系統鍵 | 不計算。 | 財務流水。 | 外部系統憑證。 | UNIQUE 防重。 | Subsidy Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
