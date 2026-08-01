# `actual_hours_adjustments` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`assignment_id` → `case_staff_assignments.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表原為人工覆寫 `case_staff_assignments.actual_hours` 的稽核日誌，但已確認 actual hours 必須唯一由正式工作日數 × 訂單每日服務時數推導。結算前以取消舊 assignment、Preview／重建新 assignment 處理；結算後以金額 adjustment／reversal 處理。本整表不再有獨立業務用途，長期考慮移除；既有資料僅供唯讀稽核。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 遺留人工工時覆寫紀錄的技術主鍵。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史 DB INSERT。 | 歷史覆寫事件。 | 不再建立新列；既有資料唯讀稽核。 | 無 | 停用 | 保留既有資料 | 人工 actual-hours 覆寫已被正式公式取代。 | 已確認：整表長期考慮移除 |
| `assignment_id` | `BIGINT NOT NULL` | 遺留覆寫對應的 assignment 關聯。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史資料。 | 歷史 assignment。 | 不再建立新列；既有資料唯讀稽核。 | 無 | 停用 | 保留既有資料 | 新流程不允許以本表改寫 assignment actual hours。 | 已確認：整表長期考慮移除 |
| `previous_actual_hours` | `DECIMAL(10, 2) NOT NULL` | 遺留覆寫前工時快照。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史資料。 | 歷史覆寫事件。 | 不再建立新列；既有資料唯讀稽核。 | 無 | 停用 | 保留既有資料 | actual hours 不再可人工覆寫。 | 已確認：整表長期考慮移除 |
| `adjusted_actual_hours` | `DECIMAL(10, 2) NOT NULL` | 遺留人工覆寫工時。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史資料。 | 歷史覆寫事件。 | 不再建立新列；結算前改由 assignment 重建，結算後改由金額 adjustment／reversal。 | 無 | 停用 | 保留既有資料 | 新寫入會破壞 actual hours 單一公式。 | 已確認：整表長期考慮移除 |
| `adjustment_reason` | `VARCHAR(255) NOT NULL` | 遺留人工覆寫原因。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史資料。 | 歷史覆寫事件。 | 不再建立新列；既有資料唯讀稽核。 | 無 | 停用 | 保留既有資料 | 新流程原因應屬取消／重建命令或金額 adjustment／reversal。 | 已確認：整表長期考慮移除 |
| `adjusted_by` | `VARCHAR(100) NOT NULL` | 遺留覆寫操作者。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史資料。 | 歷史覆寫事件。 | 不再建立新列；既有資料唯讀稽核。 | 無 | 停用 | 保留既有資料 | 不再有人工工時覆寫命令。 | 已確認：整表長期考慮移除 |
| `adjusted_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 遺留覆寫時間。 | 遺留資料／長期考慮移除 | 不計算。 | 歷史資料。 | 歷史覆寫事件。 | 不再建立新列；既有資料唯讀稽核。 | 無 | 停用 | 保留既有資料 | 不再有人工工時覆寫命令。 | 已確認：整表長期考慮移除 |
