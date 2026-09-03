# `client_payment_transaction_adjustment_allocations` 欄位權威性與計算邏輯盤點（待建）

- 狀態：已確認業務必要性；尚未進入 Schema／API／實作設計。
- 分類：`04_客戶收款與交易`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- Schema：待建；本文件不是 Schema 變更核准。
- 父表關係：`client_payment_transaction_id` → `client_payment_transactions.id`；`financial_adjustment_id` → `financial_adjustments.id`
- 子表關係：無。

## 已確認的業務規則

- 本表是客戶真實交易與共用財務調整之間的 M:N 核銷分配，不是另一張銀行交易表。
- 一筆 `stage='adjustment'` 的客戶交易可在同一次原子 Apply 中分配至同案多筆 `financial_adjustments`，但不得建立部分正式核銷。每筆被選調整在 Apply 後都必須恰好歸 0。
- 例：調整 A 應補 300、調整 B 應補 200，客戶只匯一筆 500。`client_payment_transactions` 只建立一列 500，本表建立 A=300、B=200 兩列分配，不得複製銀行交易或外部流水號。
- 每筆分配的正負效果繼承其父交易的 `transaction_type`；分配金額本身保存非負絕對值。
- 同一次原子 Apply 中，每筆所選交易的分配總和必須恰好等於該交易金額；指向每筆所選調整的同批分配加總，則必須恰好等於該調整的完整未結餘額。任一條件不成立即禁止建立 `client_payment_transactions` 與本表分配列；原始銀行流水只保留在 `finance_import_rows` 並進入財務異常／人工處理。交易與調整必須屬於同一 `case_no`。
- 每筆 `financial_adjustments` 的客戶端核銷結果，由指向該調整的成功交易分配依交易方向淨額驗證為 0；不得改用案件總實收或 `stage='adjustment'` 總額推測，也不得保存非 0 的正式核銷中間狀態。
- 本表不建立自己的 `status`、`allocation_method`、`reversal_of_allocation_id` 或備註欄位。父交易若為沖銷／退款，新增父交易及對應的新分配列；既有交易與分配均不可改寫。
- 最小欄位集合固定為：`id`、`client_payment_transaction_id`、`financial_adjustment_id`、`allocated_amount`、`created_at`。

## 已確認的最小欄位

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | 待建；建議 `BIGINT AUTO_INCREMENT PRIMARY KEY` | 交易分配列技術主鍵。 | 系統鍵 | DB 生成。 | 成功建立分配。 | 核銷分配事實。 | 保留；僅供識別與關聯，不參與金額計算。 | Finance Reconciliation Service／DB | 建立分配 | 建立後不可修改 | 無現況欄位。 | 已確認：最小子表技術鍵 |
| `client_payment_transaction_id` | 待建 | 被分配的單一真實客戶交易。 | 關聯鍵 | 不計算。 | 核銷命令。 | `client_payment_transactions.id`。 | 父交易必須為 `stage='adjustment'` 且與目標調整同案。 | Finance Reconciliation Service | 建立分配 | 建立後不可修改 | 若複製交易列代替分配，會讓銀行帳實與外部流水失真。 | 已確認採用 |
| `financial_adjustment_id` | 待建 | 本次分配核銷的共用財務調整。 | 關聯鍵 | 不計算。 | 核銷命令。 | `financial_adjustments.id`。 | 必須與父交易同案，且不得指向已取消調整。 | Finance Reconciliation Service | 建立分配 | 建立後不可修改 | 若只到案件或 adjustment stage，同案多筆調整無法個別結清。 | 已確認採用 |
| `allocated_amount` | 待建；建議 `DECIMAL(12, 2) NOT NULL` 且大於 0 | 此真實交易分配給此調整的絕對金額。 | 核銷分配事實 | 由通過完整歸零驗證的核銷 Preview 產生。 | 核銷 Preview、真實交易金額與目標調整完整未結餘額。 | `finance_import_rows` 的銀行金額、每筆調整義務與核銷分配決策。 | 保存正數；方向由父交易決定。同批 Apply 必須同時驗證：每筆交易的分配加總等於該交易金額，且每筆目標調整收到的同批分配加總等於其完整未結餘額；否則整批禁止寫入。 | Finance Reconciliation Service | 原子核銷 Apply | 建立後不可修改；更正另建反向交易與完整核銷 | 若逐列要求等於完整義務，會錯誤禁止多筆流水共同結清；若容許同批總和不歸零，則會留下部分正式核銷。 | 已確認：僅允許同批完整歸零的 M:N 分配 |
| `created_at` | 待建；建議 `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 分配列建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 原子核銷分配建立事件。 | 保留；沿用已確認技術建立時間規則，不參與交易方向、調整餘額或核銷計算。 | DB／Finance Reconciliation Service | 建立分配 | 建立後不可修改 | 不能取代父交易及原始銀行流水的正式稽核。 | 已確認：技術建立時間 |

已確認不再增加子表狀態、分配方法、反向或文字備註欄位；本文件仍只是討論提案，不代表 Schema／API／實作核准。
