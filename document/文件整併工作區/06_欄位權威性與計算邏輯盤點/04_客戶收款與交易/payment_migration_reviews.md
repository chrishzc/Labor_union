# `payment_migration_reviews` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`04_客戶收款與交易`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`case_no` → `orders.case_no`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為系統升級至 ADAD 架構時，用來存放「舊系統遺留帳務異常或無法自動對齊的資料」之**遷移覆核清單 (Migration Review)**。當所有舊案皆覆核完成且舊系統退役後，本表即可廢棄。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 遷移異常事實。 | 無。 | Migration Script | 無 | 不變 | 無 | 已確認：過渡性表格 |
| `legacy_payment_id` | `INT NOT NULL` | 舊系統 `payments` 表的主鍵。 | 關聯鍵 | 不計算。 | 舊系統。 | 舊系統 ID。 | 必須全表唯一。 | Migration Script | 無 | 不變 | 無 | 已確認 |
| `case_no` | `VARCHAR(50) NOT NULL` | 異常紀錄所屬訂單。 | 關聯鍵 | 不計算。 | 舊系統。 | `orders.case_no`。 | 無。 | Migration Script | 無 | 不變 | 無 | 已確認 |
| `legacy_caregiver_fee` | `DECIMAL(12, 2) NOT NULL` | 舊系統記錄之月嫂費用。 | 來源事實 | 不計算。 | 舊系統。 | 歷史紀錄。 | 無。 | Migration Script | 無 | 不變 | 無 | 已確認 |
| `legacy_caregiver_paid_at` | `DATE NULL` | 舊系統記錄之月嫂已付日期。 | 來源事實 | 不計算。 | 舊系統。 | 歷史紀錄。 | 無。 | Migration Script | 無 | 不變 | 無 | 已確認 |
| `reason` | `VARCHAR(255) NOT NULL` | 被判定需要人工覆核的原因。 | 來源事實 | 不計算。 | 遷移腳本判定。 | 判定邏輯。 | 無。 | Migration Script | 無 | 不變 | 無 | 已確認 |
| `review_status` | `ENUM(...) NOT NULL DEFAULT 'pending'` | 覆核狀態 (pending, resolved, dismissed)。 | 狀態欄位 | 不計算。 | 管理員操作。 | 人工覆核決策。 | 無。 | Review API | 狀態改變 | 終態凍結 | 無 | 已確認 |
| `resolved_at` | `TIMESTAMP NULL` | 完成覆核的時間。 | 來源事實 | 狀態推進時寫入。 | 系統時間。 | 決策事實。 | `review_status != 'pending'` 時必填。 | Review API | 無 | 終態凍結 | 無 | 已確認 |
| `resolution_notes` | `TEXT NULL` | 覆核備註。 | 來源事實 | 不計算。 | 人工輸入。 | 人工備註。 | 無。 | Review API | 無 | 終態凍結 | 無 | 已確認 |
