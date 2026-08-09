# `finance_import_occurrences` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`07_財務匯入與警示`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/60_finance_import_staging.sql`
- 父表關係：`batch_id` → `finance_import_batches.id`, `finance_import_row_id` → `finance_import_rows.id`
- 子表關係：無
- 已確認跨表裁決：本表為**跨批次去重複的發生位置追蹤 (Occurrence)**。因為使用者可能會不小心重複上傳包含同一筆銀行流水的 Excel 檔案。系統透過 `dedup_fingerprint` 確保 `finance_import_rows` 只有一筆唯一紀錄，而透過本前記下這筆紀錄「曾在哪些檔案的第幾列出現過」，作為溯源用。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 出現位置事實。 | 無。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `batch_id` | `BIGINT NOT NULL` | 所屬匯入批次。 | 關聯鍵 | 不計算。 | 處理當下綁定。 | `finance_import_batches.id`。 | 必須對應。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `finance_import_row_id` | `BIGINT NOT NULL` | 關聯到唯一的正規化銀行流水。 | 關聯鍵 | 不計算。 | 指紋對比。 | `finance_import_rows.id`。 | 必須對應。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `source_file` | `VARCHAR(1024) NULL` | 檔案名稱。 | 來源事實 | 不計算。 | 匯入檔案。 | 檔名。 | 無。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `sheet_name` | `VARCHAR(191) NOT NULL` | 工作表名稱。 | 來源事實 | 不計算。 | 解析檔案。 | 工作表。 | 無。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `source_row` | `INT UNSIGNED NOT NULL` | 發生在第幾列。 | 來源事實 | 不計算。 | 解析檔案。 | 行號。 | `(batch_id, sheet_name, source_row)` 必須 UNIQUE。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `warnings` | `JSON NOT NULL DEFAULT (JSON_ARRAY())` | 解析警告。 | 來源事實 | 不計算。 | 正規化錯誤。 | 解析邏輯。 | 無。 | Import Service | 無 | 寫入後凍結 | 無 | 已確認 |
