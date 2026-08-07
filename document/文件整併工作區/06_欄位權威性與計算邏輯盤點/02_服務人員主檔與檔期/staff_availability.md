# `staff_availability` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`02_服務人員主檔與檔期`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`staff_id` → `staff.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：整張表已判定為未使用之遺留 Schema (Dead Table)；實際檔期由 `caregiver_availability_locks` 及 `staff_schedule` 控制。此表將列為長期考慮移除 (Deprecate & Remove)。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 遺留主鍵。 | 遺留資料／待移除 | 無。 | 無。 | 無。 | 廢棄表。 | 無 | 停用 | 凍結 | 無任何業務邏輯寫入此表。 | 已確認：長期考慮移除 |
| `staff_id` | `INT NOT NULL` | 遺留人員關聯。 | 遺留資料／待移除 | 無。 | 無。 | 無。 | 廢棄表。 | 無 | 停用 | 凍結 | 無任何業務邏輯寫入此表。 | 已確認：長期考慮移除 |
| `start_date` | `DATE NOT NULL COMMENT '可工作開始日期'` | 遺留日期。 | 遺留資料／待移除 | 無。 | 無。 | 無。 | 廢棄表。 | 無 | 停用 | 凍結 | 無任何業務邏輯寫入此表。 | 已確認：長期考慮移除 |
| `end_date` | `DATE NOT NULL COMMENT '可工作結束日期'` | 遺留日期。 | 遺留資料／待移除 | 無。 | 無。 | 無。 | 廢棄表。 | 無 | 停用 | 凍結 | 無任何業務邏輯寫入此表。 | 已確認：長期考慮移除 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 遺留系統時間。 | 遺留資料／待移除 | 無。 | 無。 | 無。 | 廢棄表。 | 無 | 停用 | 凍結 | 無任何業務邏輯寫入此表。 | 已確認：長期考慮移除 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 遺留系統時間。 | 遺留資料／待移除 | 無。 | 無。 | 無。 | 廢棄表。 | 無 | 停用 | 凍結 | 無任何業務邏輯寫入此表。 | 已確認：長期考慮移除 |
