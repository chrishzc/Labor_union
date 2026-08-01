# `finance_alert_events` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`07_財務匯入與警示`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/90_finance_alerts.sql`
- 父表關係：`alert_id` → `finance_alerts.id`
- 子表關係：無
- 已確認跨表裁決：本表為**警示處理事件軌跡 (Event Log)**。每次改變 `finance_alerts` 的狀態（例如：工程師 A 認領了問題、會計 B 標記為已解決並補上差額），本表就會紀錄一筆不可竄改的歷史事件。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 事件發生事實。 | 無。 | Alert Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `alert_id` | `BIGINT NOT NULL` | 對應的警示主檔。 | 關聯鍵 | 不計算。 | 狀態變更觸發。 | `finance_alerts.id`。 | 必須對應。 | Alert Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `event_key` | `VARCHAR(191) NOT NULL` | 去重複鍵 (冪等)。 | 系統鍵 | 雜湊或 UUID。 | 系統產生。 | 冪等操作。 | UNIQUE。 | Alert Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `event_type` | `VARCHAR(50) NOT NULL` | 事件類型 (認領/解決/升級)。 | 來源事實 | 不計算。 | API 動作。 | 操作事實。 | 無。 | Alert Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `actor` | `VARCHAR(191) NULL` | 觸發者。 | 來源事實 | 不計算。 | 會話身分。 | 操作事實。 | 允許為系統。 | Alert Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `event_snapshot` | `JSON NOT NULL` | 當時警示與環境的 JSON 快照。 | 歷史快照 | 變更當下凍結。 | `finance_alerts` 狀態。 | 當時情境。 | 供稽核與溯源用。 | Alert Service | 無 | 寫入後凍結 | 無 | 已確認 |
