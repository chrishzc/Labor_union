# `finance_alerts` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`07_財務匯入與警示`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/90_finance_alerts.sql`
- 父表關係：無
- 子表關係：`finance_alert_events`
- 已確認跨表裁決：本表為**人工介入的對帳異常任務 (Human-in-the-loop Task)**。例如：「客戶繳的錢與應收不符」、「找不到這筆匯款是誰匯的」等。這類似於 Issue Tracker，負責追蹤異常案件直到解決為止。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 警示事實。 | 無。 | Alert Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `alert_key` | `VARCHAR(191) NOT NULL` | 唯一去重鍵。 | 系統鍵 | 雜湊。 | 系統計算。 | 防止相同錯誤重複發布。 | UNIQUE。 | Alert Service | 無 | 不變 | 無 | 已確認 |
| `alert_code` | `VARCHAR(100) NOT NULL` | 警示代碼 (例如短繳)。 | 來源事實 | 不計算。 | 異常拋出點。 | 異常類型。 | 無。 | Alert Service | 無 | 不變 | 無 | 已確認 |
| `source_*` | `VARCHAR(100)` | 異常發生的物件定位。 | 多型關聯 | 不計算。 | 拋出點提供。 | 發生源。 | 無。 | Alert Service | 無 | 不變 | 無 | 已確認 |
| `expected_amount` / `actual_amount` | `DECIMAL(18, 2) NULL` | 預期與實際金額差異。 | 來源事實 | 拋出時傳入。 | 系統比對結果。 | 金額事實。 | 無。 | Alert Service | 無 | 不變 | 無 | 已確認 |
| `status` | `ENUM(...) NOT NULL DEFAULT 'open'` | 任務狀態 (開啟/認領/已解決)。 | 狀態欄位 | 依據處理推進。 | 人工操作。 | 任務進度。 | `open -> claimed -> resolved`。 | Alert API | 狀態改變 | 終態凍結 | 無 | 已確認 |
| `claimed_by` / `resolved_by` | `VARCHAR(191) NULL` | 處理者。 | 來源事實 | 不計算。 | 會話身分。 | 操作事實。 | 無。 | Alert API | 無 | 不變 | 無 | 已確認 |
