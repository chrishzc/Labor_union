# `staff_payment_transactions` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`staff_payment_id` → `staff_payments.id`
- 子表關係：無
- 已確認跨表裁決：本表是既有的**月嫂單一 assignment 匯款帳本**，與已確認的整月核銷模型重複。新流程以 `staff_monthly_settlements` 作唯一付款義務、以 `staff_actual_transfers` 保存正式銀行事件，不需要為同一出款再建立 assignment 級交易。**整張表標記為新流程停寫、歷史相容唯讀、長期考慮移除**；既有正式交易不得改寫。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 舊交易技術主鍵。 | 歷史相容鍵 | 不計算。 | DB 自增。 | 舊正式交易。 | 新流程不再建立。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與月結正式匯款事件重複。 | 長期考慮移除 |
| `staff_payment_id` | `BIGINT NOT NULL` | 舊流程所屬 assignment 應付。 | 歷史相容關聯 | 不計算。 | 舊交易流程。 | `staff_payments.id`。 | 新流程不做 assignment 級銀行交易。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 把月結付款拆成不必要的單案交易。 | 長期考慮移除 |
| `case_no` | `VARCHAR(50) NOT NULL` | 舊交易所屬訂單。 | 歷史相容關聯 | 不計算。 | 舊交易流程。 | `orders.case_no`。 | 新流程由月結明細保留訂單組成。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與月結明細重複。 | 長期考慮移除 |
| `staff_id` | `INT NOT NULL` | 舊交易匯款對象。 | 歷史相容關聯 | 不計算。 | 舊交易流程。 | `staff.id`。 | 新流程由月結 Header 與正式轉帳保存。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與兩張新流程主表重複。 | 長期考慮移除 |
| `transaction_type` | `ENUM('transfer', 'reversal', 'return') NOT NULL` | 舊交易方向。 | 歷史相容事實 | 不計算。 | 舊交易流程。 | 舊匯款方向。 | 新流程方向事實只保存於 `staff_actual_transfers`。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 雙帳本可能產生方向不一致。 | 長期考慮移除 |
| `transaction_status` | `ENUM('succeeded', 'failed', 'reversed') NOT NULL` | 舊交易狀態。 | 歷史相容狀態 | 不計算。 | 舊銀行對帳。 | 舊過帳結果。 | 新流程只讀 `staff_actual_transfers.transaction_status`。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 雙帳本狀態可能漂移。 | 長期考慮移除 |
| `amount` | `DECIMAL(12, 2) NOT NULL` | 舊 assignment 級交易金額。 | 歷史相容事實 | 不計算。 | 舊銀行流水或人工輸入。 | 舊匯款金額。 | 新流程只保存 `staff_actual_transfers.amount`。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與正式月結轉帳金額重複。 | 長期考慮移除 |
| `occurred_at` | `DATE NULL` | 舊 assignment 級匯款日。 | 歷史相容事實 | 不計算。 | 舊銀行流水。 | 舊匯款日期。 | 新流程只保存正式月結轉帳日期。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 同一次月結匯款可能被複製到多筆 assignment。 | 長期考慮移除 |
| `external_reference` | `VARCHAR(100) NULL` | 舊 assignment 級銀行流水號。 | 歷史相容鍵 | 不計算。 | 舊銀行資料匯入。 | 舊外部憑證。 | 新流程外部憑證只由原始流水與 `staff_actual_transfers` 保存。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 同一流水號在雙帳本重複。 | 長期考慮移除 |
| `reversal_of_transaction_id` | `BIGINT NULL` | 舊交易沖銷關聯。 | 歷史相容關聯 | 不計算。 | 舊沖銷操作。 | 舊交易歷史。 | 新流程沖銷只在 `staff_actual_transfers` 鏈上處理。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 雙沖銷鏈會增加一致性負擔。 | 長期考慮移除 |
| `notes` | `TEXT NULL` | 舊 assignment 級交易備註／人工原因。 | 歷史相容文字事實 | 舊 UI 建立交易時必填。 | 舊 `staff_payment_transactions` API caller。 | 舊人工交易操作。 | 新流程的更正原因應跟隨 `staff_actual_transfers` 的正式退匯／沖銷事件或其稽核事件，不再寫入本表。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 與已停寫的單 assignment 交易流程綁定。 | 長期考慮移除 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 舊交易建立時間。 | 歷史相容技術時間 | DB 建立時寫入。 | DB 時鐘。 | 舊交易建立事件。 | 本表停寫；既有值只供歷史追查。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 隨整表退出新流程。 | 長期考慮移除 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 舊交易最後更新時間。 | 歷史相容技術投影 | DB 於列更新時覆寫。 | 舊交易列更新。 | 舊流程最近異動。 | 本表停寫；既有值只供歷史追查。 | 無新寫入 Owner | 無 | 既有資料不改寫 | 隨整表退出新流程。 | 長期考慮移除 |
