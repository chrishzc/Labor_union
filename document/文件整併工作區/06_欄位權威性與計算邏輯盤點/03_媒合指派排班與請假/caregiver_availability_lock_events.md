# `caregiver_availability_lock_events` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/99b_caregiver_availability_lock_events.sql`
- 父表關係：`lock_id` → `caregiver_availability_locks.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為檔期鎖定的「不可變事件稽核日誌 (Immutable Event Log)」，追蹤鎖定的取得 (acquired)、釋放 (released)、轉換為正式指派 (converted) 或取消 (cancelled) 的確切時間點與原因。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 事件事實。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `lock_id` | `BIGINT NOT NULL` | 所屬批次。 | 關聯鍵 | 不計算。 | 業務請求。 | `caregiver_availability_locks.id`。 | 必須對應有效批次。 | Availability Lock Service | 無 | 不變 | 無 | 已確認 |
| `event_type` | `ENUM(...) NOT NULL` | 事件類型 (acquired, released, converted, cancelled)。 | 來源事實 | 不計算。 | 服務層判定。 | 操作事實。 | 必須反映鎖定批次的狀態變更。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 軌跡 |
| `event_key` | `VARCHAR(100) NOT NULL` | 冪等鍵。 | 系統鍵 | 不計算。 | UUID 產生。 | 請求事實。 | 必須全域唯一。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `actor` | `VARCHAR(100) NOT NULL` | 執行操作的管理員或系統角色。 | 來源事實 | 不計算。 | Session 或排程器。 | 登入或系統身分。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `reason` | `TEXT NULL` | 事件原因。 | 來源事實 | 不計算。 | 手動輸入或系統產生。 | 業務說明。 | acquired 可為 NULL，其餘必填。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `payload` | `JSON NOT NULL` | 事件當下上下文快照。 | 來源事實 | JSON 序列化。 | 服務層收集。 | 變更參數。 | 必須為合法 JSON Object。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `occurred_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 事件發生時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
