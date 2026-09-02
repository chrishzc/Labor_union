# `staff_bookings` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`02_服務人員主檔與檔期`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`staff_id` → `staff.id`, `client_id` → `clients.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：
  1. **SSOT 界定**：月嫂與案件的正式排班，唯一事實來源 (SSOT) 應為 `staff_schedule` 與 `case_staff_assignments` 模型。
  2. **作廢標記**：`staff_bookings` 被正式標記為「遺留／待移除 (Legacy/To be removed)」，未來不再有任何業務邏輯依賴此表。
  3. **髒點標記**：目前在 `line/line_bot.py` 內於合約簽署時直接呼叫 SQL 寫入 `staff_bookings` 的邏輯屬於重大架構違規，未來必須重構為呼叫標準的 Domain Service 產生狀態機事件與 `staff_schedule` 投影。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 遺留的技術主鍵。 | 遺留資料／待移除 | DB 自增。 | DB INSERT。 | 無（遺留邏輯）。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 與 `staff_schedule` 衝突。 | 已確認：長期考慮移除 |
| `staff_id` | `INT NOT NULL` | 指向月嫂的外鍵。 | 遺留資料／待移除 | 不計算。 | 遺留 line_bot.py 寫入。 | 實際指派事實。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 與 `staff_schedule` 衝突。 | 已確認：長期考慮移除 |
| `client_id` | `INT NOT NULL` | 指向客戶的外鍵。 | 遺留資料／待移除 | 不計算。 | 遺留 line_bot.py 寫入。 | 實際指派事實。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 新架構應使用 `orders.case_no` 而非直接關聯客戶。 | 已確認：長期考慮移除 |
| `start_date` | `DATE NOT NULL COMMENT '服務開始日期'` | 逐日排班日期。 | 遺留資料／待移除 | 不計算。 | 遺留 line_bot.py 寫入。 | 訂單服務日期。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 實際排班應存放於 `staff_schedule.work_date`。 | 已確認：長期考慮移除 |
| `end_date` | `DATE NOT NULL COMMENT '服務結束日期'` | 逐日排班日期（同 start_date）。 | 遺留資料／待移除 | 不計算。 | 遺留 line_bot.py 寫入。 | 訂單服務日期。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 實際排班應存放於 `staff_schedule.work_date`。 | 已確認：長期考慮移除 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 系統建立時間。 | 遺留資料／待移除 | DB 自動寫入。 | DB。 | 寫入時間。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 無 | 已確認：長期考慮移除 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 系統更新時間。 | 遺留資料／待移除 | DB 自動寫入。 | DB。 | 更新時間。 | 本表已作廢，應長期移除。 | 遺留 line_bot.py | 寫入時 | 凍結 | 無 | 已確認：長期考慮移除 |
