# Staff Payables 與 Client Refund 正式規格

## 1. 文件狀態與裁決

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- Staff Payables 月結裁決：`confirmed-inherited`
- Client Refund 納入正式 Client Finance：`consolidated-decision`
- Client Refund implementation status：`partial`
- 本文件覆蓋舊稿中「人工月結 aggregate」與「一般客戶退款 deferred／missing」的矛盾。
- 當前核准只啟用 Inventory v2 evidence；本文件 Commands、schema、pytest 與
  legacy exit 條款是未來 Work Package contract，不是本輪執行授權。

## 2. Domain：Staff Payables

### 2.1 責任與 SSOT

Staff Payables 擁有：

- Payroll 已建立之 assignment-owned 月嫂應付義務的付款生命週期與投影；
- 正式銀行出款、退匯／沖正的 immutable ledger event；
- payout event 與 payable obligation 的 allocation／link；
- `payable | completed | anomaly` 衍生投影；
- 應付款清單、同月嫂彙總與 XLSX 歸檔。

Staff Payables 不擁有：

- 訂單狀態、服務日、薪資公式或義務初始金額；
- 客戶退款義務；
- 人工 month-end close、draft、finalized、revision 或 paid 月結狀態機。

### 2.2 根事實與衍生值

根事實：

1. Payroll 產生的 immutable staff payable obligation；
2. assignment identity、正式服務日與 rate snapshot；
3. canonical bank payout fact；
4. payout／return／reversal ledger event；
5. obligation allocation／link；
6. bank account identity snapshot；
7. aggregate version 與 idempotency receipt。

衍生值：

- 應付餘額；
- `payable | completed | anomaly`；
- 指定付款日應付款清單；
- 同一月嫂、同一付款日的 XLSX 聚合列；
- payout anomaly 與重新應付狀態。

`staff_monthly_settlements`、`staff_monthly_settlement_details`、
`staff_actual_transfers`、`staff_payment_transactions` 與
`staff_transfer_allocations` 只作歷史查詢／遷移來源，不得形成新流程依賴。
live `staff_payments` 若存在，只能是 canonical Payroll obligation 的 compatibility
projection，不得成為第二個義務 SSOT 或被 Staff Payables 反向改寫。

### 2.3 Subsystem：Payable Obligation Projection

責任：把 Payroll 已提交的 obligation event 投影成 Staff Payables root facts。

Modules：

- `StaffPayableObligationConsumer`
- `StaffPayableIdentity`
- `StaffPayableProjectionReducer`
- `StaffPayableVersionGate`

不變量：

- obligation identity 唯一且可重播；
- 金額為正整數 NTD；
- 來源必須綁定 assignment 與 rate snapshot；
- 來源事件重送不得建立第二筆義務；
- adjustment 建立新不可變 event／allocation，不修改舊義務歷史。

### 2.4 Subsystem：Payout Reconciliation

Commands：

- `PreviewStaffPayout`
- `ApplyStaffPayout`
- `PreviewStaffPayoutReturn`
- `ApplyStaffPayoutReturn`
- `PreviewStaffPayoutReversal`
- `ApplyStaffPayoutReversal`

共同 Apply 交易：

1. 以 canonical staff mutex order 取得 lock；
2. 鎖定 aggregate version、bank facts、bank account snapshot 與 obligations；
3. 重建 candidate，驗證 Preview fingerprint 與 expected version；
4. 依事件別 guard 驗證；
5. append payout／return／reversal event；
6. append obligation links；
7. 更新 projection、version、outbox 與 receipt；
8. 由 outer Unit of Work 單次 commit。

事件別 guard：

- payout：選定銀行出款與選定 payable obligation 精確相等；
- return：必須指向一筆仍有效的 payout 與 canonical 銀行退匯入款，重開相同義務；
- reversal：必須指向一筆仍有效的錯誤 payout，不要求銀行入款，但要求人工 reason、
  operation capability 與不可重複沖正；
- return／reversal 都不得超過目標 payout 的尚未重開金額。

正式核銷不得留下「部分完成」。不足、超付、帳戶不一致或 allocation 不唯一時，
整筆不建立正式 payout，轉 typed blocker／anomaly。

### 2.5 Global／Application Subsystem：Accounts Payable Query／Export

本 Subsystem 置於本文件是為了記錄帳務來源契約；正式 owner 是跨 Domain
read-only reporting application，不是 Staff Payables Domain。它只能透過 Staff Payables
與 Client Finance typed view ports 組合輸出，不擁有 ledger 或付款狀態。

Query：

- `QueryAccountsPayable(target_payment_date)`
- `QueryAccountsPayableArchive(year)`

Export：

1. 在一致 read snapshot 讀取 `payable` obligations，以及 review=`normal` 的
   `pending`／`partially_refunded` 客戶退款義務；
2. 月嫂列依 `staff_id + target_payment_date + bank_identity` 聚合；
3. anomaly／completed／refunded／review-required 不進應付款清單；
4. client refund row 只輸出 remaining amount，並明確標示
   `customer_refund` 或 `subsidy_return`，不得重複輸出已清償金額；
   `subsidy_return` 的 target payment date 是結案月份加兩個曆月的 15 日，且列必須
   顯示為 `client_subsidy_return`，不得與月嫂 payout 合併或抵銷；
5. 只生成一次 workbook bytes；
6. 使用者下載 bytes 與 archive bytes 必須完全相同；
7. archive 名稱不可覆蓋，保存 SHA-256 receipt；
8. Query／下載／歸檔不改變 payable 狀態。

XLSX 是輸出快照，不是月結 entity。

### 2.6 Typed errors

| Code | 類型 | 處理 |
|---|---|---|
| `staff_payable_not_found` | not-found | 重新 Query |
| `staff_payable_candidate_stale` | stale | 重新 Preview |
| `idempotency_conflict` | conflict | 拒絕重用不同 payload |
| `staff_obligation_not_exactly_settled` | blocker | 人工核對銀行事實與義務 |
| `staff_bank_account_ambiguous` | blocker | 人工確認唯一有效帳戶 |
| `staff_payout_amount_mismatch` | blocker | 人工核對銀行金額與義務 |
| `staff_payout_reversal_invalid` | blocker | 不得 reversal-of-reversal 或超額 |
| `transaction_failed` | transaction | 只有 storage unavailable／deadlock／timeout 標 retryable |
| `accounts_payable_export_has_anomaly` | blocker | 異常中心處理 |
| `accounts_payable_archive_failed` | external | 不宣稱匯出完成 |

### 2.7 人工入口與異常

- 管理員只能從應付款 Query 選定 bank facts 與 obligations 後 Preview／Apply。
- `PAYOUT-001`～`003` 由 root facts 投影；認領／解除不取代修正根事實。
- 退匯／沖正成功後，既有義務重新成為 `payable`。

### 2.8 Legacy exit

1. 所有 `staff_monthly_settlements*` production writer 停止；
2. legacy staff payment transaction route 固定 `410 Gone`；
3. adjustment 不得寫入「下一個未 finalized 月結」；
4. `finance_import_dispatch` 不得再寫 `staff_actual_transfers` 或月結 candidate；
5. writer inventory 與 runtime tests 證明無正式 caller；
6. 保留資料只經 versioned preserve-data migration，不直接 DROP 歷史表。

## 3. Domain：Client Finance／Customer Refund

### 3.1 責任與 SSOT

Client Finance 擁有：

- 客戶 refund obligation；
- canonical bank outflow 與 immutable refund ledger entry；
- refund entry 對 refund obligation 的 exact allocation；
- account version、outbox、receipt 與目前投影；
- receipt reversal 後重新形成的 receivable。

退款不解除已成立的不可逆案件服務資料鎖，也不改變 Orders 已發生的服務事實。

### 3.2 Refund 與 Reversal 排他

| Operation | 根事實 | 結果 |
|---|---|---|
| Customer Refund | 已成立 refund obligation＋正式銀行出款 | 清償退款義務 |
| Subsidy Return | 已成立 subsidy-return obligation＋正式銀行出款 | 清償客戶預付補助退還義務；季度第一月結案案件的付款日為結案月加兩曆月 15 日 |
| Receipt Reversal | 既有有效 receipt ledger event 失效 | append reversal 並重開原 receivable |

禁止：

- 用負數收款表示退款；
- 更新或刪除原 receipt；
- 把 refund 當 receipt reversal；
- reversal-of-reversal；
- 無 refund obligation 時依人工輸入金額直接付款；
- 因退款解鎖服務資料或倒退 Orders lifecycle。

每一筆 canonical bank outflow 必須全額分配，不得留下不明餘額；同一 refund obligation
可以由多筆不可變銀行出款逐步清償，因此 obligation 可以有 `partially_refunded` 投影。
任何 allocation 都不得使累積有效退款超過 obligation amount。

一般退款 ledger entry type 固定為 `refund`，其退匯／沖正固定為
`refund_reversal`；客戶補助退還則固定為 `subsidy_return`，其退匯／沖正固定為
`subsidy_return_reversal`。兩條線不得共用 transaction type、remaining balance 或
progress reducer。`reversal` 只可用於原 client receipt 的沖正。

### 3.3 Subsystem：Refund Obligation Planning

Commands：

- `CreateCustomerRefundObligation`
- `CreateSubsidyReturnObligation`
- `AdjustRefundObligation`

root fact 必須來自已提交的 cancellation／financial adjustment／subsidy-return 業務事件。
每個 obligation 保存 source event identity、case number、integer amount、reason、
version 與 immutable creation event。

### 3.4 Subsystem：Refund／Reversal Preview and Apply

Queries／Commands：

- `QueryClientRefundReversal`
- `PreviewClientRefund`
- `ApplyClientRefund`
- `PreviewClientSubsidyReturn`
- `ApplyClientSubsidyReturn`
- `PreviewClientReceiptReversal`
- `ApplyClientReceiptReversal`
- `PreviewClientRefundReturn`
- `ApplyClientRefundReturn`
- `PreviewClientRefundReversal`
- `ApplyClientRefundReversal`

Preview：

- 選定 canonical bank fact 與 obligation／reversal target；
- 驗證同一 case、operation purpose、金額、唯一性與目前 account version；
- 建立 deterministic allocation 與 fingerprint；
- 零寫入。

Apply：

1. 檢查 idempotency receipt；
2. 鎖定 Client Finance account、bank facts、obligations 或 reversal targets；
3. 重建 candidate；
4. 驗證 expected account version 與 Preview fingerprint；
5. append ledger entries 與 allocations；
6. 精確套用本次 refund allocation 並重算 remaining；remaining 為零才標示
   `refunded`，receipt reversal 則重開 receivable；
7. 更新 projection、version、outbox 與 receipt；
8. outer Unit of Work 單次 commit。

每一筆選定 bank outflow 的金額必須被精確分配；不足 obligation 全額時形成
`partially_refunded`，超過 remaining refundable amount 時整筆拒絕。

### 3.5 State machine

Refund obligation 使用兩個正交衍生投影，避免把人工覆核進度混入付款進度：

```text
refund_progress:
not_required
pending ──valid partial allocation──> partially_refunded
pending／partially_refunded ──remaining amount exactly zero──> refunded
refunded ──valid refund return／reversal event──> pending | partially_refunded

refund_review:
normal ↔ review_required
```

正式 refund ledger event append 後不可改寫。銀行退匯若需要重新應退，必須新增
dedicated reversal／reopen event，不得刪除原 refund。

Refund return／reversal 的 target 必須是仍有效的 refund ledger entry。return 另須綁定
canonical 銀行退匯入款；reversal 需要人工 reason 與 operation capability。兩者都使用
expected account version、Preview fingerprint 與各自 stable idempotency key，在 Client
Finance outer Unit of Work 內 append dedicated reopen event、重算 progress、寫 receipt
與 outbox 後單次 commit。不同 payload 重用 key、stale target、重複 return／reversal
一律 conflict；只有 storage unavailable／deadlock／timeout 可安全重試。

### 3.6 Typed errors

| Code | 類型 | 處理 |
|---|---|---|
| `client_finance_case_not_found` | not-found | 停止 |
| `client_obligation_not_found` | not-found／stale | 重新 Query |
| `client_finance_candidate_stale` | stale | 重新 Preview |
| `client_finance_version_conflict` | conflict | 重新 Query |
| `idempotency_conflict` | conflict | 拒絕不同 payload |
| `invalid_client_refund_intent` | validation | 修正選擇 |
| `client_refund_bank_allocation_incomplete` | blocker | 每筆銀行出款未被完整分配 |
| `client_refund_exceeds_remaining_amount` | blocker | 拒絕超額退款 |
| `client_refund_return_invalid` | blocker | 退款退匯／沖正目標無效 |
| `client_receipt_reversal_invalid` | blocker | 不得超額或重複沖正 |
| `client_finance_storage_unavailable` | retryable | 安全重試／查 receipt |

### 3.7 人工入口與異常

- UI 顯示 backend Query 的 bank facts、refund obligations、account version 與 blockers。
- Apply 必須沿用同一次 Preview 的 fingerprint 與 stable idempotency key。
- 金額不符、多義對象、缺 bank identity 或歷史資料不可唯一還原時，維持 open 並進
  Anomalies；不得猜測 allocation。

### 3.8 Legacy exit

- 舊「本階段不支援一般退款」標為 superseded。
- 任何直接更新 `client_payments` summary、負收款、覆寫原 transaction 或跨案抵銷路徑退出。
- Data Browser 不得修改 refund／receipt ledger。

### 3.9 Implementation gaps

下列缺口未關閉前，Client Refund 不得標為 `proven`：

1. Finance Import／bank classifier 產生正式 `client_refund` canonical classification；
2. production dispatch 以 borrowed Client Finance Unit of Work 完成退款核銷；
3. `partially_refunded`／`refunded`／`review_required` reducer；
4. refund failure 與 canonical refund anomaly workflow（bank return 已有 Finance Import manual correction→borrowed Client Finance UoW 的 typed workflow，但尚無自動分類）；
5. canonical refund anomalies 與全域退款待辦；
6. Accounts Payable Export 明確區分 `customer_refund` 與 `subsidy_return`；
7. Module、Subsystem、隔離 MySQL Domain 與 Global E2E 全部通過；
8. writer inventory 證明負收款、原交易覆寫與 legacy refund caller 已退出。

## 4. 交易與跨 Domain 邊界

- cancellation／adjustment 產生 refund obligation 時，由相應 Global coordinator 的
  outer Unit of Work 同交易委派 Client Finance。
- 實際銀行退款核銷由 Client Finance 擁有，不回寫 Orders lifecycle。
- Accounts Payable Export 可以唯讀合併 staff payable 與 client refund rows，
  但不能在同一 Query 中互相抵銷。
- Finance Import 只提供 canonical bank facts，透過 borrowed Unit of Work 委派
  Client Finance 或 Staff Payables，不直接寫正式 ledger。

## 5. 分層驗收

### Module

- integer NTD、exact allocation、deterministic ordering、reversal guards；
- payout／refund projection reducer；
- workbook aggregation、bytes digest 與 filename。

### Subsystem

- Preview 零寫入；
- Apply replay、idempotency mismatch、stale、rollback、retry；
- refund／reversal 排他；
- payout return／reversal 重開義務；
- archive failure 不宣稱完成。

### Domain

- 隔離 MySQL 驗證 FK、unique、append-only trigger、row lock 與單次 commit；
- 同月嫂多訂單聚合不建立月結；
- 每筆 bank outflow exact allocation，obligation 可逐筆清償並於餘額歸零後 refunded。

### Global

- cancellation／adjustment→refund obligation→bank refund；
- Payroll→staff payable→payout／return；
- Finance Import dispatch 不繞過 owning Domain；
- client refund 與 staff payout 同批存在但互不抵銷；
- failure injection 證明跨 Domain transaction 全部 rollback。

## 6. 來源追溯

- `04_Client_Finance_Domain.md`
- `05_Staff_Payables_Export_Domain.md`
- `07_跨Domain交易與pytest驗收架構.md`
- `13_規格實作完成度矩陣.md`
- `document/文件整併工作區/02_訂單帳務與資料處理_無損合併稿.md`
- `document/文件整併工作區/05_潛在狀態機規則盤點.md`
- `document/文件整併工作區/06_欄位權威性與計算邏輯盤點.md`
- `domains/client_finance/client_refund_reversal.py`
- `subsystems/client_finance/client_refund_reversal_workflow.py`
- `domains/staff_payables/reconciliation.py`
- `subsystems/staff_payables/payout_reconciliation.py`
- `subsystems/staff_payables/accounts_payable_export.py`

live files只證明目前已有相符結構，不會因存在而自動取得規格權威。
