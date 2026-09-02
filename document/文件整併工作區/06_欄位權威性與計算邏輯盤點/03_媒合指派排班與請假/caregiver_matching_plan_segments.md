# `caregiver_matching_plan_segments` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/98_caregiver_matching_plans.sql`
- 父表關係：`plan_id` → `caregiver_matching_plans.id`, `staff_id` → `staff.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為配對方案的「區段明細 (Detail 表)」。設計上支援「同一案件由多個月嫂接力完成」，因此限制 `segment_order` 介於 1 至 4，並透過 `UNIQUE KEY` 限制同一方案內同一月嫂只能出現一次。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 區段的技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 提案區段事實。 | 無。 | Matching Plan Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `plan_id` | `BIGINT NOT NULL` | 所屬方案 Header。 | 關聯鍵 | 不計算。 | 建立邏輯。 | `caregiver_matching_plans.id`。 | 必須有效對應。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `segment_order` | `TINYINT NOT NULL` | 區段順序 (1 至 4)。 | 來源事實 | 不計算。 | 建立時依序分配。 | 月嫂接力順序。 | 必須介於 1 到 4。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 被指派/推薦的月嫂 ID。 | 關聯鍵 | 不計算。 | 管理員選擇。 | `staff.id`。 | 必須有效且在同一方案內唯一。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `assigned_start_date` | `DATE NOT NULL` | 該區段預計服務開始日。 | 來源事實 | 不計算。 | 管理員輸入。 | 預定排程。 | `start_date <= end_date`。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `assigned_end_date` | `DATE NOT NULL` | 該區段預計服務結束日。 | 來源事實 | 不計算。 | 管理員輸入。 | 預定排程。 | `start_date <= end_date`。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 建立時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
