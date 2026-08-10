# `assignment_schedule_leave_substitution_events` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/101_assignment_schedule_leave_substitution_events.sql`
- 父表關係：`case_no` → `orders.case_no`, `original_assignment_id` → `case_staff_assignments.id`, `substitute_assignment_id` → `case_staff_assignments.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表作為不可變的子事件日誌，負責記錄每一次「請假/順延/代班」的確切處置結果，以及關聯的排班與薪資快照。本表為查詢該指派為何變更排班或工時的唯一稽核來源 (SSOT)。最終狀態已同步至排班表與指派表，但歷史追溯皆以本表為準。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 事件事實。 | 無。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬案件編號。 | 關聯鍵 | 不計算。 | 繼承自 Batch。 | `orders.case_no`。 | 必須對應有效訂單。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `original_assignment_id` | `BIGINT NOT NULL` | 被請假或異動的原始月嫂指派。 | 關聯鍵 | 不計算。 | 業務邏輯。 | `case_staff_assignments.id`。 | 必須對應有效指派。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `original_schedule_id` | `INT NOT NULL` | 被異動的原始排班紀錄 ID。 | 關聯鍵 | 不計算。 | 業務邏輯。 | `staff_schedule.id`。 | 必須對應有效排班。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `work_date` | `DATE NOT NULL` | 發生異動的實際請假日期。 | 來源事實 | 不計算。 | 前端請求/邏輯解析。 | 月嫂實際請假日。 | 必須為排班紀錄中的有效日期。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `resolution_type` | `ENUM(...) NOT NULL` | 處置類型 (僅請假/順延/尋找代班)。 | 來源事實 | 不計算。 | 業務邏輯判定。 | 使用者決策與系統規則。 | 必須符合列舉的處置策略。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 處置策略 |
| `substitute_assignment_id` | `BIGINT NULL` | 代班者的指派紀錄。 | 關聯鍵 | 不計算。 | 若為代班，則創建並關聯新指派。 | `case_staff_assignments.id`。 | 當 `resolution_type = substitute` 時必填。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `event_key` | `VARCHAR(100) NOT NULL` | 本事件的全域冪等鍵。 | 系統鍵 | 不計算。 | UUID 產生。 | 事件唯一性。 | 必須全域唯一。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `actor` | `VARCHAR(100) NOT NULL` | 操作員。 | 來源事實 | 不計算。 | Session 帶入。 | 登入身分。 | 無。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `reason` | `VARCHAR(255) NOT NULL` | 處置原因。 | 來源事實 | 不計算。 | 手動輸入。 | 使用者輸入。 | 無。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `schedule_snapshot` | `JSON NOT NULL` | 變更當下的排班快照。 | 來源事實 | JSON 序列化。 | 服務層擷取當下排班。 | 排班狀態事實。 | 必須保存處置當下的確切內容。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `payroll_snapshot` | `JSON NOT NULL` | 變更當下的薪資核對快照。 | 來源事實 | JSON 序列化。 | 服務層擷取當下薪資。 | 薪資狀態事實。 | 必須保存處置當下的確切內容。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `occurred_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 發生時間。 | 來源事實 | DB 自動填入。 | DB。 | 系統時間。 | 無。 | Leave Substitution Service | 無 | 寫入後凍結 | 無 | 已確認 |
