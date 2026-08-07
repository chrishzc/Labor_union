# `assignment_schedule_leave_substitution_batches` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/102_assignment_schedule_leave_substitution_batches.sql`
- 父表關係：`case_no` → `orders.case_no`
- 子表關係：`batch_key` → `assignment_schedule_leave_substitution_events.event_key` (概念上對應同一批)
- 已確認跨表裁決：本表與 events 表構成標準的領域事件溯源 (Event Sourcing) 結構。本表為「請假/順延/代班」這類複合業務操作的**聚合根與不可變批次日誌**，負責記錄冪等鍵、防篡改校驗碼與請求原始快照，以保證操作邊界與稽核追溯能力。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `batch_key` | `VARCHAR(100) NOT NULL PRIMARY KEY` | 冪等鍵，唯一識別一次批次處理。 | 系統鍵 | 不計算。 | UUID 或 API 產生。 | 請求事實。 | 必須全域唯一。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `case_no` | `VARCHAR(50) NOT NULL` | 本批次事件所屬案件。 | 關聯鍵 | 不計算。 | 業務邏輯傳入。 | `orders.case_no`。 | 必須有效對應訂單。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `preview_fingerprint` | `CHAR(64) NOT NULL` | 預覽快照的 SHA256，用於防篡改校對。 | 系統鍵 | Hash 計算。 | 服務層預先計算。 | 預覽計算結果。 | 一經計算固定不變。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `item_count` | `INT UNSIGNED NOT NULL` | 該批次包含的事件總數。 | 衍生計算 | COUNT(events)。 | 服務層傳入。 | 子事件數量。 | 必須嚴格等於對應的 events 數量。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `actor` | `VARCHAR(100) NOT NULL` | 執行此批次操作的管理員識別。 | 來源事實 | 不計算。 | API Session。 | 登入身分。 | 無。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `reason` | `VARCHAR(255) NOT NULL` | 統一操作原因。 | 來源事實 | 不計算。 | 手動輸入。 | 使用者輸入。 | 不能為空。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `request_snapshot` | `JSON NOT NULL` | API 請求原始資料快照。 | 來源事實 | JSON 序列化。 | API Payload。 | HTTP Request 內容。 | 必須完整保留請求結構。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `occurred_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 批次建立時間。 | 來源事實 | DB 自動填入。 | DB。 | 系統時間。 | 無。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
