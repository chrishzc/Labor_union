# `caregiver_availability_lock_days` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/99a_caregiver_availability_locks.sql`
- 父表關係：`lock_id` → `caregiver_availability_locks.id`, `segment_id` → `caregiver_matching_plan_segments.id`, `staff_id` → `staff.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為等待訂金階段的「逐日／逐月嫂占用鎖定明細 (Detail)」。除 assignment 服務區間外，每個 assignment 預計結束日後 7 天都必須以獨立 `buffer` 鎖定事實預留；buffer 與正式服務日語意分離，但同樣參與同月嫂同日不可重複占用。整案第一個正式服務開始時解除全部 buffer，正式服務區間鎖不受影響。現況 Schema 沒有 `lock_kind`，且要求 `lock_date` 位於 segment 內，無法合法表示 post-segment buffer，屬已確認架構缺口。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 鎖定明細事實。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `lock_id` | `BIGINT NOT NULL` | 所屬批次。 | 關聯鍵 | 不計算。 | 業務請求。 | `caregiver_availability_locks.id`。 | 必須對應有效批次。 | Availability Lock Service | 無 | 不變 | 無 | 已確認 |
| `segment_id` | `BIGINT NOT NULL` | 對應的方案子區段。 | 關聯鍵 | 不計算。 | 業務請求解析。 | `caregiver_matching_plan_segments.id`。 | 必須對應有效的子區段。 | Availability Lock Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 月嫂 ID。 | 關聯鍵 | 不計算。 | 從 Segment 解析。 | `staff.id`。 | 必須對應方案中規劃的月嫂。 | Availability Lock Service | 無 | 不變 | 無 | 已確認 |
| `lock_date` | `DATE NOT NULL` | 被佔用的檔期日期；可屬正式 segment 區間或該 segment 結束後 7 天 buffer。 | 來源事實 | 服務區間逐日展開；buffer 為 `segment_end + 1` 至 `segment_end + 7`。 | Segment 日期與鎖定類型。 | 方案規劃之連續占用區間與預留緩衝政策。 | 服務區間鎖須落在 Segment 日期內；buffer 鎖須明確標記為 buffer 並落在 Segment 結束後 7 天，不得計入 assignment 服務日、`actual_hours` 或薪資。 | Availability Lock Service | 方案鎖定、轉正式或整案首次服務開始 | 建立後不改日期；解除以 active marker／事件表達 | 現況沒有 `lock_kind` 且 schema constraint 只允許 segment 內日期，不能表示已確認 buffer 規則；實作前需正式 Schema／契約裁決。 | 已確認規則；現況模型缺口 |
| `active_marker` | `TINYINT(1) NULL` | 供 Unique Key 使用的鎖定旗標。 | 系統鍵 | 有效為 1，解除為 NULL。 | 狀態機邏輯。 | `locks.status` 對應。 | Header 解除時此處必須同步解除。 | Availability Lock Service | 狀態改變 | 終態凍結 | 無 | 已確認 |
| `released_by` | `VARCHAR(100) NULL` | 解除鎖定的管理員。 | 來源事實 | 不計算。 | Header 解除時同步帶入。 | 系統或登入身分。 | `active_marker IS NULL` 時必填。 | Availability Lock Service | 解除時寫入 | 終態凍結 | 無 | 已確認 |
| `created_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 建立時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `released_at` | `TIMESTAMP NULL` | 解除時間。 | 來源事實 | 狀態推進時寫入。 | 系統時間。 | 解鎖事實時間。 | `active_marker IS NULL` 時必填。 | Availability Lock Service | 解除時寫入 | 終態凍結 | 無 | 已確認 |
