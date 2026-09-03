# `staff_actual_transfers` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：演算法完成
- 規格反查：已完成

- Schema：`db/schema_parts/40_staff_actual_transfers.sql`
- 父表關係：現況 `settlement_id` → `staff_monthly_settlements.id`, `staff_id` → `staff.id`；提案新增 `finance_import_row_id` → `finance_import_rows.id`
- 子表關係：現況 Schema 有 `staff_transfer_allocations`；新流程停寫，僅供歷史資料讀取。
- 已確認跨表裁決：原始出款流水先保存在 `finance_import_rows`；本表只保存**已通過整張月份月結完整核銷的月嫂正式銀行轉帳事件**。同一月嫂同月多筆訂單先加總於一張 `staff_monthly_settlements`；同次 Apply 可使用一筆或多筆出款，但成功出款的方向淨額必須恰好等於整張月結 `total_payable`，才可原子建立正式轉帳並將月結標為 `paid`。不再把出款回配至月結明細或薪資構成。不符時留在匯入／異常層，現況允許 `partially_paid` 屬實作漂移。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 匯款事實。 | 無。 | Transfer Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `settlement_id` | `BIGINT NOT NULL` | 對應的月結單。 | 關聯鍵 | 不計算。 | API 綁定。 | `staff_monthly_settlements.id`。 | 必須對應。 | Transfer Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 匯款對象。 | 關聯鍵 | 不計算。 | API 綁定。 | `staff.id`。 | 必須對應。 | Transfer Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `payment_phase` | `ENUM('normal', 'first_salary', 'second_subsidy', 'unknown') NOT NULL DEFAULT 'unknown'` | 現況用來把月嫂出款區分為一般／第一階段薪資／第二階段舊制補助。 | 歷史相容分類／待移除 | 現況 caller 必須傳入 `normal`、`first_salary` 或 `second_subsidy`；`second_subsidy` 會要求原始流水分類為 `staff_legacy_subsidy`，其餘要求 `staff_salary`。 | 現況 caller 與匯入分類結果。 | 舊制分階段付款流程。 | 長期考慮移除。新流程不再寫入或依本欄判斷；付款來源只決定訂單應付月份，正式銀行事件只核銷整張月結。既有值僅供歷史唯讀。 | 新流程無寫入 Owner | 無新寫入 | 既有正式事件不改寫 | 把已停用的舊制補助與逐構成付款帶入正式匯款事件，會與整月一次完整核銷衝突。 | 已確認：歷史唯讀，長期考慮移除 |
| `transaction_type` | `ENUM('transfer', 'return', 'reversal') NOT NULL` | 交易方向 (匯出/退匯/沖銷)。 | 來源事實 | 不計算。 | 銀行流水。 | 匯款方向。 | 無。 | Transfer Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `transaction_status` | `ENUM(...) NOT NULL DEFAULT 'succeeded'` | 交易狀態。 | 狀態欄位 | 不計算。 | 銀行對帳結果。 | 實際過帳狀態。 | 只有 `succeeded` 才參與月結實付方向淨額計算。 | Transfer Service | 銀行回報 | 終態凍結 | 無 | 已確認 |
| `amount` | `DECIMAL(12, 2) NOT NULL` | 單筆正式銀行轉帳金額。 | 來源事實 | 不計算。 | 銀行流水。 | 匯款金額。 | 同次 Apply 中屬於同一月結的成功轉帳依 `transaction_type` 計算方向淨額後，必須恰好等於該月結 `total_payable`；單筆轉帳不必等於整月總額。 | Transfer Service | 無 | 寫入後凍結 | 若再要求等於逐明細 allocation 加總，會重複保存一套沒有獨立業務意義的分配。 | 已確認：月結 Header 層完整歸零 |
| `occurred_at` | `DATE NULL` | 實際銀行轉帳日。 | 來源事實 | 不計算。 | 銀行流水。 | 日期。 | 無。 | Transfer Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `source_bank` | `VARCHAR(100) NOT NULL` | 名稱看似出款銀行，但現況實際保存匯入格式識別。 | 歷史相容快照／待移除 | 現況直接保存 `finance_import_rows.format_id`，不是銀行名稱欄位。 | `finance_import_rows.format_id`。 | 匯入檔格式識別。 | 長期考慮移除。建立正式 `finance_import_row_id` 關聯後新流程停寫；既有值僅作歷史格式快照，不得解讀為銀行名稱或參與計算。 | 新流程無寫入 Owner | 無新寫入 | 既有正式事件不改寫 | 欄名是 bank，實際 writer 卻存 format ID，且重複原始流水已有資訊。 | 已確認：歷史唯讀，長期考慮移除 |
| `source_account` | `VARCHAR(100) NULL` | 工會實際出款帳號快照。 | 歷史相容快照／待移除 | 不計算。 | `finance_import_rows.source_bank_account`。 | 原始銀行流水的出款帳號。 | 長期考慮移除。建立正式 `finance_import_row_id` 關聯後新流程停寫；既有值只供歷史唯讀，不參與薪資或核銷計算。 | 新流程無寫入 Owner | 無新寫入 | 既有正式事件不改寫 | 與原始流水重複保存相同出款帳號。 | 已確認：歷史唯讀，長期考慮移除 |
| `counterparty_account` | `VARCHAR(100) NULL` | 實際入帳的月嫂帳號快照。 | 不可變稽核快照 | 不計算。 | `finance_import_rows.resolved_counterparty_account`，並與 `staff_bank_accounts` 驗證唯一 owner。 | 銀行流水解析出的收款帳號。 | 保留；保存核銷當下經唯一月嫂身分驗證後採用的實際收款帳號，不具獨立權威性，不參與薪資計算，也不得以月嫂日後更新的銀行主檔回寫。 | Remittance Service | 核銷 Apply | 寫入後不變 | 現況具完整唯一 owner 驗證。 | 已確認：保留不可變收款帳號快照 |
| `external_reference` | `VARCHAR(191) NOT NULL` | 現況以衍生 fingerprint 字串充當正式匯款冪等識別。 | 衍生相容系統鍵／待移除 | 現況不是銀行提供的流水號，而是 `fp:{finance_import_rows.dedup_fingerprint}`。 | `finance_import_rows.dedup_fingerprint`。 | 原始銀行流水主鍵及其去重指紋。 | 長期考慮移除。直接 `finance_import_row_id` 關聯建立並以 UNIQUE 防重後，新流程停寫；既有值只供歷史相容，不得解讀為銀行流水號。 | 新流程無寫入 Owner | 無新寫入 | 既有正式事件不改寫 | 原盤點把它誤認為銀行流水號；實際只是由另一衍生值包裝出的字串。 | 已確認：直接原始流水關聯建立後停寫並長期考慮移除 |
| `reversal_of_transfer_id` | `BIGINT NULL` | 退匯／沖銷事件所指向的原正式匯款。 | 不可變因果關聯鍵 | `transfer` 時必須為空；`return`／`reversal` 時必須指向原事件。 | 退匯／沖銷命令。 | 原 `staff_actual_transfers.id`。 | 保留。原交易不可覆寫；更正事件必須以本欄指向原匯款並形成可追溯反向鏈。 | Remittance Service | 退匯／沖銷 Apply | 寫入後不變 | 符合不可變正式帳本原則。 | 已確認：保留不可變退匯／沖銷關聯 |
| `raw_import_reference` | `VARCHAR(255) NULL` | 原始匯入流水的字串關聯。 | 衍生相容關聯／待移除 | 現況固定產生 `finance_import_row:{finance_import_row_id}`。 | `finance_import_rows.id`。 | 原始銀行流水主鍵。 | 長期考慮移除。改由直接 `finance_import_row_id` 外鍵取代；新流程停寫本欄，既有字串只供歷史唯讀。 | 新流程無寫入 Owner | 無新寫入 | 既有正式事件不改寫 | 需要解析字串且缺乏 FK 完整性，又與 `external_reference` 同時保存兩個衍生識別。 | 已確認：改用直接原始流水外鍵，長期考慮移除 |
| `review_status` | `ENUM('not_required', 'pending', 'confirmed') NOT NULL DEFAULT 'pending'` | 現況正式匯款事件的人工覆核狀態。 | 歷史相容狀態／待移除 | 現況正常核銷成功時直接寫 `confirmed`；`payment_phase='unknown'` 時 Schema 強制 `pending`。 | 現況核銷 Service 與 `payment_phase`。 | 舊 phase／allocation 推斷流程。 | 長期考慮移除。新流程不再寫入；不符合完整核銷條件的資料只能留在 `finance_import_rows`／警示層，正式匯款一旦建立即代表核銷成立，不另掛覆核狀態。既有值只供歷史唯讀。 | 新流程無寫入 Owner | 無新寫入 | 既有正式事件不改寫 | 沒有獨立人工覆核事件或 review API，且會讓不確定資料看似可先進正式帳本再處理。 | 已確認：歷史唯讀，長期考慮移除 |
| `created_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 正式匯款事件建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 正式事件建立時點。 | 沿用已確認技術時間規則；不取代 `occurred_at`，也不參與金額計算。 | DB／Remittance Service | 建立事件 | 建立後不變 | 無。 | 已確認：沿用技術建立時間規則 |

## 已確認提案欄位

| 提案欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `finance_import_row_id` | 現況不存在；提案 `BIGINT NOT NULL`，FK → `finance_import_rows.id`，並以 UNIQUE 防止同一原始流水重複正式入帳 | 正式匯款直接指向其唯一原始銀行流水。 | 不可變來源關聯鍵 | 不計算。 | 核銷 Preview 所選 `finance_import_rows.id`。 | 原始銀行流水主鍵。 | 每筆正式匯款／退匯／沖銷事件都必須直接指向自己的原始流水；不得以 fingerprint 或可解析字串取代 FK。 | Remittance Service | 原子核銷 Apply | 寫入後不變 | 現況只有 `external_reference` 與 `raw_import_reference` 兩個衍生字串，無 FK 完整性。 | 已確認採用；僅為提案，尚未核准 Schema 實作 |
