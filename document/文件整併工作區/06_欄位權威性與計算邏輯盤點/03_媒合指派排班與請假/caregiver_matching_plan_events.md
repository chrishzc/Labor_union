# `caregiver_matching_plan_events` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/99_caregiver_matching_plan_events.sql`
- 父表關係：`plan_id` → `caregiver_matching_plans.id`, `segment_id` → `caregiver_matching_plan_segments.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為配對方案與區段操作的「不可變事件稽核日誌 (Immutable Event Log)」。包含向月嫂發送意願確認信 (`info_1_sent`, `info_2_sent`)、月嫂意願改變 (`willingness_changed`)、發送履歷給客戶 (`resume_sent`) 以及方案取消等操作的生命週期歷史追溯。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 事件事實。 | 無。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `plan_id` | `BIGINT NOT NULL` | 關聯之方案。 | 關聯鍵 | 不計算。 | 業務請求。 | `caregiver_matching_plans.id`。 | 必須對應有效方案。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `segment_id` | `BIGINT NULL` | 關聯之區段（若為區段層級事件）。 | 關聯鍵 | 不計算。 | 業務請求。 | `caregiver_matching_plan_segments.id`。 | 若涉及特定月嫂區段則必填。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `event_type` | `ENUM(...) NOT NULL` | 事件類型 (如 info_1_sent)。 | 來源事實 | 不計算。 | 服務層判定。 | 操作事實。 | 必須依賴 `chk_caregiver_matching_plan_events_target` 檢查對應之 `segment_id` 是否為空。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 軌跡 |
| `event_key` | `VARCHAR(100) NOT NULL` | 冪等鍵。 | 系統鍵 | 不計算。 | UUID 產生。 | 請求事實。 | 必須全表唯一。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `actor` | `VARCHAR(100) NOT NULL` | 執行操作的管理員或角色。 | 來源事實 | 不計算。 | Session 或系統。 | 登入身分。 | 無。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `payload` | `JSON NOT NULL` | 事件上下文與操作參數快照。 | 來源事實 | JSON 序列化。 | 服務層收集。 | 變更參數。 | 必須為合法 JSON Object。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `occurred_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 發生時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Matching Plan Service | 無 | 寫入後凍結 | 無 | 已確認 |
