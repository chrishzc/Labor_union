# `matching_records` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`case_no` → `orders.case_no`, `staff_id` → `staff.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表已被 ADAD 新架構的 `caregiver_matching_plans` 與 `caregiver_matching_plan_events` 完全取代。此表為**「遺留／待移除 (Legacy/Dead Table)」**，不應再有新邏輯依賴它。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 遺留的技術主鍵。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 本表已作廢，應長期移除。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `case_no` | `VARCHAR(50) NOT NULL` | 遺留的案件關聯。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 本表已作廢，應長期移除。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `staff_id` | `INT NOT NULL` | 遺留的月嫂關聯。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 本表已作廢，應長期移除。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `caregiver_accepted` | `TINYINT NULL` | 遺留的接受意願狀態。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 由 `caregiver_matching_plan_events.willingness_changed` 取代。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `sent_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 遺留的發送時間。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 由 `caregiver_matching_plan_events` 取代。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `replied_at` | `TIMESTAMP NULL` | 遺留的回覆時間。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 由 `caregiver_matching_plan_events` 取代。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `sent_info_1_at` | `DATETIME NULL` | 遺留的訂單資訊-1 發送時間。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 由 `caregiver_matching_plan_events.info_1_sent` 取代。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `sent_info_2_at` | `DATETIME NULL` | 遺留的訂單資訊-2 發送時間。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 由 `caregiver_matching_plan_events.info_2_sent` 取代。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
| `sent_resume_at` | `DATETIME NULL` | 遺留的履歷發送時間。 | 遺留資料／待移除 | 不計算。 | 遺留程式碼。 | 無。 | 由 `caregiver_matching_plan_events.resume_sent` 取代。 | 遺留邏輯 | 無 | 凍結 | 與 `matching_plans` 重疊且資訊過時。 | 已確認：長期考慮移除 |
