# `staff_bank_accounts` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`staff_id` → `staff.id`
- 子表關係：無
- 已確認跨表裁決：本表為**月嫂銀行帳戶 (SSOT)**。支援 1:N 多組帳戶，並透過 `is_primary` 旗標決定預設匯款帳號。從 `staff` 主表中抽離，符合第三正規化 (3NF)。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 帳戶事實。 | 無。 | Staff Profile API | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `staff_id` | `INT NOT NULL` | 所屬月嫂。 | 關聯鍵 | 不計算。 | 綁定操作。 | `staff.id`。 | 必須對應有效月嫂。 | Staff Profile API | 無 | 不變 | 無 | 已確認 |
| `bank_code` | `VARCHAR(10) COMMENT '銀行代碼(3碼)'` | 銀行代碼。 | 來源事實 | 不計算。 | 月嫂輸入。 | 存摺事實。 | 必須為 3 碼數字。 | Staff Profile API | 無 | 不變 | 無 | 已確認 |
| `branch_code` | `VARCHAR(10) COMMENT '分行代碼(4碼)'` | 分行代碼。 | 來源事實 | 不計算。 | 月嫂輸入。 | 存摺事實。 | 視銀行決定是否必填。 | Staff Profile API | 無 | 不變 | 無 | 已確認 |
| `account_no` | `VARCHAR(50) NOT NULL` | 銀行帳號。 | 來源事實 | 不計算。 | 月嫂輸入。 | 存摺事實。 | 必須純數字。 | Staff Profile API | 無 | 不變 | 無 | 已確認 |
| `is_primary` | `BOOLEAN DEFAULT TRUE` | 是否為主要預設帳戶。 | 狀態欄位 | 不計算。 | 系統預設或手動切換。 | 用戶決策。 | 同一月嫂應只能有一個 `is_primary = TRUE`。 | Staff Profile API | 切換時 | 不變 | 無 | 已確認 |
