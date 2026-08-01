# `order_assignment_change_audits` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/96_order_assignment_sync_audit.sql`
- 父表關係：`case_no` → `orders.case_no`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為不可變的事件稽核日誌 (Immutable Event Log)，負責記錄當「配對方案 (`caregiver_matching_plans`)」正式被套用、寫入 `case_staff_assignments` 時的同步稽核快照。經盤點確認移除 `order_before_snapshot`，以符合 Lazy 最小化儲存原則。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 事件事實。 | 無。 | Order Sync Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬案件編號。 | 關聯鍵 | 不計算。 | 業務請求。 | `orders.case_no`。 | 必須對應有效訂單。 | Order Sync Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `order_before_snapshot` | `JSON NOT NULL` | 套用前訂單快照。 | 來源事實 | JSON序列化。 | 服務層擷取。 | 變更前狀態。 | 系統目前從未讀取此欄位。 | Order Sync Service | 無 | 寫入後凍結 | 浪費儲存空間 (YAGNI)。 | 已確認：作廢並移除 |
| `order_after_snapshot` | `JSON NOT NULL` | 套用後訂單快照。 | 來源事實 | JSON序列化。 | 服務層擷取。 | 變更後狀態。 | 稽核防禦用途，不可刪除。 | Order Sync Service | 無 | 寫入後凍結 | 無 | 已確認：保留稽核用 |
| `assignment_plan_snapshot` | `JSON NOT NULL` | 套用的配對方案快照。 | 來源事實 | JSON序列化。 | 服務層擷取。 | 套用的方案內容。 | 稽核防禦用途，不可刪除。 | Order Sync Service | 無 | 寫入後凍結 | 無 | 已確認：保留稽核用 |
| `applied_by` | `VARCHAR(100) NOT NULL` | 操作管理員。 | 來源事實 | 不計算。 | Session。 | 登入身分。 | 無。 | Order Sync Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `applied_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 套用時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Order Sync Service | 無 | 寫入後凍結 | 無 | 已確認 |
