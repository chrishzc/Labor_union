# `subsidy_claim_batches` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`06_政府補助與申請`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/70_subsidy_claim_batches.sql`
- 父表關係：無
- 子表關係：`subsidy_claim_batch_items`, `government_subsidy_transactions`
- 已確認跨表裁決：本表為**正式季度政府補助申請批次 (Header)**。以「年度」與「季度」為單位向政府送件，並支援修訂版。本表負責加總追蹤申請總額 (`requested_amount`)、政府核准總額 (`approved_amount`) 與實際已撥款分配總額 (`paid_amount`)，是申請進度與總量控管的核心。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 批次事實。 | 無。 | Subsidy Claim Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `application_year` | `SMALLINT UNSIGNED NOT NULL` | 申請年度。 | 來源事實 | 不計算。 | 建立時指定。 | 業務週期。 | 無。 | Subsidy Claim Service | 無 | 送件後凍結 | 無 | 已確認 |
| `quarter` | `TINYINT UNSIGNED NOT NULL` | 申請季度 (1~4)。 | 來源事實 | 不計算。 | 建立時指定。 | 業務週期。 | 必須在 1 到 4 之間。 | Subsidy Claim Service | 無 | 送件後凍結 | 無 | 已確認 |
| `revision` | `INT UNSIGNED NOT NULL` | 修訂版。 | 系統鍵 | 不計算。 | 建立流程提供。 | 送件次數。 | 必須 >= 1，同年度/季度內遞增唯一。 | Subsidy Claim Service | 無 | 不變 | 無 | 已確認 |
| `status` | `ENUM(...) NOT NULL DEFAULT 'draft'` | 批次狀態。 | 狀態欄位 | 不計算。 | 系統邏輯與撥款推進。 | 送件與過帳事實。 | 必須符合 `chk_subsidy_claim_batch_state_times` 狀態機約束。 | Subsidy Claim Service | 狀態改變 | 終態凍結 | 無 | 已確認 |
| `requested_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 申請總額。 | 衍生計算 | SUM(items.requested)。 | 明細表投影。 | 送件時凍結明細。 | 不受後續核准與撥款覆寫。 | Subsidy Claim Service | 送件結算 | 送件後凍結 | 無 | 已確認 |
| `approved_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 核准總額。 | 衍生計算 | SUM(items.approved)。 | 明細表投影。 | 政府公文。 | 不覆寫申請總額。 | Subsidy Claim Service | 公文匯入 | 核准後凍結 | 無 | 已確認 |
| `paid_amount` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 已撥分配總額。 | 衍生計算 | SUM(allocations)。 | 分配矩陣投影。 | 金流與分配。 | 由 `government_subsidy_allocations` 加總。 | Subsidy Remittance Service | 分配或沖銷 | 終態凍結 | 無 | 已確認 |
| `submitted_at` | `DATETIME NULL` | 送件時間。 | 來源事實 | 不計算。 | 狀態變更寫入。 | 操作事實。 | `status != 'draft'` 必填。 | Subsidy Claim Service | 無 | 終態凍結 | 無 | 已確認 |
| `approved_at` | `DATETIME NULL` | 核准時間。 | 來源事實 | 不計算。 | 狀態變更寫入。 | 操作事實。 | `status IN ('approved', ...)` 必填。 | Subsidy Claim Service | 無 | 終態凍結 | 無 | 已確認 |
