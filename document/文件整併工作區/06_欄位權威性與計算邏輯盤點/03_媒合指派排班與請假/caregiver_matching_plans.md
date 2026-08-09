# `caregiver_matching_plans` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/98_caregiver_matching_plans.sql`
- 父表關係：`case_no` → `orders.case_no`
- 子表關係：`caregiver_matching_plan_segments` (方案區段明細), `caregiver_matching_plan_events` (生命週期與操作稽核)
- 已確認跨表裁決：本表為「洽談中訂單案件的配對方案 Header 表」。採用嚴格的版本控管 (version)，確保同一案件只有一個有效版本 (`is_active = 1`)。本表是整個業務「月嫂推薦媒合階段」的核心領域實體 (Domain Entity) 與唯一狀態事實來源 (SSOT)。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 方案的技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 提案事實。 | 無。 | Matching Plan Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬洽談中訂單編號。 | 關聯鍵 | 不計算。 | 建立時傳入。 | `orders.case_no`。 | 必須有效對應訂單。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `version` | `INT NOT NULL DEFAULT 1` | 方案版本號。 | 系統鍵 | 舊版 + 1。 | 建立邏輯。 | 迭代次數。 | 同一案件中遞增，唯一。 | Matching Plan Service | 新增草稿時 | 不變 | 無 | 已確認 |
| `status` | `ENUM(...) NOT NULL DEFAULT 'draft'` | 方案狀態 (draft, proposed, accepted, rejected, superseded, cancelled)。 | 狀態欄位 | 狀態機推進。 | 業務邏輯與 API 呼叫。 | 操作與客戶決策事實。 | 必須遵循嚴格的狀態轉換。 | Matching Plan Service | 狀態改變 | 終態凍結 | 無 | 已確認：SSOT 狀態 |
| `is_active` | `TINYINT(1) NULL` | 供 Unique Key 使用的有效旗標。 | 系統鍵 | 有效為 1，無效為 NULL。 | 狀態機邏輯。 | `status` 對應。 | 同一案件只能有一個 1。 | Matching Plan Service | 狀態改變 | 終態凍結 | 無 | 已確認 |
| `start_date` | `DATE NOT NULL` | 方案完整服務開始日。 | 來源事實 | 不計算。 | 建立方案時輸入或由 Segments 推導。 | 客戶需求與排程事實。 | `start_date <= end_date`。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `end_date` | `DATE NOT NULL` | 方案完整服務結束日。 | 來源事實 | 不計算。 | 建立方案時輸入或由 Segments 推導。 | 客戶需求與排程事實。 | `start_date <= end_date`。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `created_by` | `VARCHAR(100) NOT NULL` | 建立此方案版本的管理員識別。 | 來源事實 | 不計算。 | Session。 | 登入身分。 | 無。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 建立時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Matching Plan Service | 無 | 不變 | 無 | 已確認 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE ...` | 更新時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Matching Plan Service | 無 | 無 | 無 | 已確認 |
