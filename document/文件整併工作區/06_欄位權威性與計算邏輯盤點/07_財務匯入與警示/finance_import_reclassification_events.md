# `finance_import_reclassification_events` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`07_財務匯入與警示`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/61_finance_import_reprocessing.sql`
- 父表關係：`finance_import_row_id` → `finance_import_rows.id`
- 子表關係：無
- 已確認跨表裁決：本表為**重新分類事件 (Event Log/Audit)**。當系統認不出匯款人是誰，或者認錯了，需要會計人員手動修正其對應身分 (Client/Staff) 時，本表記錄了修改的「前因後果與溯源快照」。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 變更事件。 | 無。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `run_id` | `BIGINT NOT NULL` | 重啟任務的 ID。 | 關聯鍵 | 不計算。 | 關聯鍵。 | `finance_import_reprocess_runs.id`。 | 必須對應。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `finance_import_row_id` | `BIGINT NOT NULL` | 被修改的流水行。 | 關聯鍵 | 不計算。 | 操作綁定。 | `finance_import_rows.id`。 | 必須對應。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `actor` | `VARCHAR(255) NOT NULL` | 執行修改的人。 | 來源事實 | 不計算。 | 會話身分。 | 身分事實。 | 必填。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `before_*` | `VARCHAR/JSON` | 修改前的身分與理由。 | 歷史快照 | 修改前資料。 | 原始資料拷貝。 | 原有分類狀態。 | 無。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `after_*` | `VARCHAR/JSON` | 修改後的身分與理由。 | 歷史快照 | 操作者決定。 | 變更請求。 | 新分類狀態。 | 無。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `dispatch_result` | `VARCHAR(100) NOT NULL` | 分派結果 (成功/失敗)。 | 來源事實 | 不計算。 | 對帳系統回應。 | 處置結果。 | 無。 | Reprocessing Service | 無 | 寫入後凍結 | 無 | 已確認 |
