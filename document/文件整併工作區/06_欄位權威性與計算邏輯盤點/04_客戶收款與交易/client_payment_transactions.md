# `client_payment_transactions` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`04_客戶收款與交易`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`, `db/schema_parts/65_client_payment_finance_link.sql`
- 父表關係：`client_payment_id` → `client_payments.id`, `case_no` → `orders.case_no`, `finance_import_row_id` → `finance_import_rows.id`
- 子表關係：提案中的 `client_payment_transaction_adjustment_allocations` 將 `stage='adjustment'` 的一筆真實交易分配至一筆或多筆 `financial_adjustments`
- 已確認跨表裁決：本表為**已通過完整核銷的客戶正式交易帳本**。原始銀行事實先保存在 `finance_import_rows`；只有同一次核銷 Preview 能讓每筆所選金流完整分配、每筆所選義務核銷後恰好為 0，才可原子寫入本表及其分配。少收、多收、錯匯或任何未打平情況不得建立部分正式交易，應留在匯入／異常層。正式寫入後為 Immutable Transaction：原收款保留為 `succeeded`，退款或沖銷另建反向交易。訂金、頭款、尾款仍各自獨立，不得跨期抵銷；`stage='subsidy_return'` 是工會退還客戶補助的獨立出款。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 金流明細的技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 交易事實。 | 無。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `client_payment_id` | `BIGINT NOT NULL` | 所屬的收款帳務主表 ID。 | 關聯鍵 | 不計算。 | 前端請求/API。 | `client_payments.id`。 | 必須對應有效帳戶。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 前端請求。 | `orders.case_no`。 | 必須與主表 `case_no` 一致。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `stage` | `ENUM('deposit', 'first_payment', 'second_payment', 'subsidy_refund', 'subsidy_return', 'adjustment') NOT NULL` | 收款安排或款項來源的業務標籤。 | 來源事實 | 不計算。 | 登帳時指定。 | 收款目的事實。 | `deposit`、`first_payment`、`second_payment` 各自是獨立核銷階段，僅與同名應收比較；少匯、多匯、錯匯與跨期挪用均進異常／人工處理，不能由其他階段抵銷。`adjustment` 必須對應 `financial_adjustments` 的一筆共用財務調整並單獨核銷。`subsidy_return` 是工會退還客戶補助的獨立出款；`subsidy_refund` 已標記長期考慮移除。 | Transaction Service | 新增交易 | 寫入後凍結 | 若把 `subsidy_return` 混入服務費淨實收，或以三期總額抵銷跨期差異，會遺失異常。 | 已確認：三期與 adjustment 均獨立核銷 |
| `transaction_type` | `ENUM('receipt', 'refund', 'reversal') NOT NULL` | 交易方向（向客戶收款／退還客戶／帳務沖銷）。 | 來源事實 | 不計算。 | 登帳時指定。 | 金流方向事實。 | `receipt` 對應摘要淨額 `+amount`；`refund`、`reversal` 對應 `-amount`。反向交易必須另建新列，不得改寫原交易。 | Transaction Service | 新增反向交易 | 寫入後凍結 | 無 | 已確認：以方向決定正負 |
| `transaction_status` | `ENUM('succeeded', 'failed', 'reversed') NOT NULL DEFAULT 'succeeded'` | 交易狀態。 | 狀態欄位 | 不計算。 | 第三方金流或人工覆核。 | 銀行實際入帳狀態。 | 僅 `succeeded` 交易按 `transaction_type` 參與淨額加總。不得將已成功的原收款改為 `reversed` 來抵銷；應新增成功的 `refund`／`reversal` 列。 | Transaction Service | 金流失敗或新增反向交易 | 終態凍結 | 現況列舉值 `reversed` 容易誘導回寫原列；新規則不以它處理已成功交易的更正。 | 已確認：原收款維持 succeeded |
| `amount` | `DECIMAL(12, 2) NOT NULL` | 交易金額。 | 來源事實 | 不計算。 | 銀行流水或人工輸入。 | 實際金流金額。 | 一律存非負絕對金額；正負效果僅由 `transaction_type` 決定。例：先收 2,100（`receipt`），後退 2,100（`refund`），摘要淨額為 0。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 數值 |
| `occurred_at` | `DATE NULL` | 實際發生或銀行入帳日期。 | 來源事實 | 不計算。 | 銀行流水或人工輸入。 | 實際入帳日。 | 無。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `external_reference` | `VARCHAR(100) NULL` | 銀行流水號或第三方金流唯一識別碼。 | 系統鍵 | 不計算。 | 第三方金流。 | 外部系統憑證。 | 若有金流串接則必填且唯一 (防重複入帳)。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `finance_import_row_id` | `BIGINT NULL`（由 migration 65 新增） | 對應 canonical 財務匯入流水；人工補登允許為空。 | 關聯鍵 | 不計算。 | 財務匯入核銷流程。 | `finance_import_rows.id`。 | 自動核銷交易必須精確指向唯一匯入列；人工補登才可為 `NULL`。 | Finance Reconciliation Service | 正式交易建立 | 寫入後凍結 | 原清冊漏列此既有欄位與外鍵。 | 已確認：財務流水關聯 |
| `reversal_of_transaction_id` | `BIGINT NULL` | 本次若是沖銷，指向被沖銷的原始交易 ID。 | 關聯鍵 | 不計算。 | 沖銷操作帶入。 | `client_payment_transactions.id`。 | 沖銷時必填。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `notes` | `TEXT NULL` | 備註。 | 來源事實 | 不計算。 | 手動輸入。 | 人工備註。 | 無。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 建立時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Transaction Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 最近更新時間。 | 技術中繼資料 | DB 自動填入。 | DB。 | 最近異動時間。 | 只供技術稽核；不可作為實際入帳、退款或核銷日期。 | DB | 任一 UPDATE | 可變 | 原清冊漏列。 | 已確認：技術時間 |
