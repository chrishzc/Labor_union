# Staff Payables／Accounts Payable Export

## 1. 分責

`Staff Payables` 管理月嫂付款義務、銀行出款、退匯／reversal、精確核銷及 payable／completed／anomaly 投影。

`Accounts Payable Export` 是跨 Domain 唯讀 reporting subsystem，組合 Staff Payables 與 Client Finance 的客戶補助退還義務。

不建立 Monthly Settlement Domain、header、revision、draft、finalized 或下載狀態。

## 2. Staff Payables SSOT

| 概念 | 唯一權威 |
|---|---|
| 原始銀行支出 | Finance Import `CanonicalOutgoingBankFactPort` |
| 月嫂付款義務 | Payroll 產生的 assignment-owned immutable obligation events，以及其 `staff_obligations` current projection；`staff_payments` 僅 compatibility projection |
| payout／return／reversal | immutable Staff Payout Ledger |
| 銀行帳戶 owner | 唯一有效 primary `staff_bank_accounts` |
| net paid | succeeded payout − return − reversal |
| balance | obligation − net paid |
| due date | Orders `staff_payment_due_date`：衍生客戶應收大於 0 為結案後次月 15 日；應收為 0 且本案符合全補助訂單（補助市民、時數不超過 120、樓層費及自費皆為 0）才為結案後第二曆月 15 日 |
| 同月合併 | Query／export projection |

狀態：

```text
balance = obligation 且 net_paid = 0 → payable
balance = 0 → completed
部分、超付、ownership／帳戶／金額不符 → anomaly
退匯／reversal 使 net_paid 不足 → payable
```

不建立正式 `partially_paid`。

全補助訂單的月嫂義務仍屬本 Domain；它只是不經 Client Finance 的客戶收款核銷。補助資格案若有超額時數或樓層費，仍先走客戶收款路徑。付款日到而全補助訂單的政府款尚未入帳時，資金來源以 Government Subsidy 的工會墊付處理；該 funding fact 不得改寫月嫂義務、也不得變成客戶退款。

## 3. Subsystems

### Payable Query

選取有效 obligations，依 `staff_id + target payment month` 聚合顯示，但保留所有 `staff_payment_ids`、case numbers 與逐筆金額。聚合不落 DB entity。

### Payout Reconciliation Preview

驗證所有銀行列為 outgoing debit、同一月嫂、帳戶 owner 唯一、所選義務完整應付，且支出總額恰等於完整義務合計。禁止半筆義務、部分付款、超付、跨 staff 或重複 raw fact。

### Payout Apply

目標資料模型：

```text
staff_payout_events
  event_type: payout | return | reversal
  status: succeeded
  amount_ntd
  finance_import_row_id
  reversal_of_event_id
  idempotency_key

staff_payout_obligation_links
  payout_event_id
  staff_payment_id
  allocated_amount_ntd
```

正式 ledger 只保存實際成功的 payout／return／reversal；失敗嘗試留在 bank staging／anomaly，不混入正式帳本。每筆 obligation 必須完整 allocation。

### Historical Payout Evidence／Settlement（2026-08-28 人工裁決）

對使用系統前且已正式採納的 historical case，首要付款證據仍是 Finance Import canonical outgoing
bank fact，能正常對應時走既有 Payout Reconciliation。舊銀行／帳務證據缺失、歸屬不明或無法可靠
還原時，才允許歷史人工 `paid | settled` Q/P/A。Apply 必須綁定 exact case、staff、payer=工會、
payee=月嫂、selected obligations及historical adoption，保存actor、reason、evidence、expected version、
fingerprint、idempotency、receipt與outbox；付款日期不明時保存unknown，不得偽填。

客戶付款給工會、Orders completed、應付清冊下載、客戶補助退款或政府撥款都不能推定月嫂已付款。
歷史 `paid` 只建立選定staff obligations的付款事實；`settled`只終止本Domain選定obligations，不改
Client Finance。後續return、reversal、薪資／服務更正或新obligation依較新owner event重開或更新；
舊event保持immutable。不得偽造bank row／allocation、跨staff合併或提供generic payable status editor。
完整跨Domain契約見
`../02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md`。

第 `27` 份正式規格新增的「歷史訂單－帳務完成」只可消費本 Domain 的正式逐 obligation settlement
facts：每位月嫂 balance 都必須為 0，且無 payout／return／reversal binding blocker。Payroll 已依歷史
`actual_service_days` 建立義務或只完成應付清冊下載，都不能推定月嫂款項已實際結清。

### Payable Anomaly Facts

輸出 `PAYOUT-001` 到期未匯、`PAYOUT-002` 原應付日後才形成或改變、`PAYOUT-003` 銀行主檔不完整，以及 ownership／共享帳戶／金額不符。人工 resolve 不修改義務或付款投影。

## 4. Accounts Payable Export

資料來源：

- `StaffPayableExportSource`
- `ClientRefundExportSource`

流程：

```text
一致性 read transaction 讀取當下 payable
→ 排除 completed 與 anomaly
→ 同月同月嫂多訂單合併
→ 驗證帳戶、整數金額、付款日與來源
→ 產生一次 XLSX bytes
→ SHA-256
→ 原子保存 downloads/accounts_payable_archive/YYYY/
→ 驗證 archive hash
→ 成功後回傳完全相同 bytes
```

檔名包含目標付款日、產生日期時間及 short hash，永不覆蓋。Archive 失敗不下載；下載不改付款狀態；XLSX 本身就是當次快照，不另建 DB 快照。

## 5. Legacy compatibility

新架構停止依賴：

- `staff_monthly_settlements`
- `staff_monthly_settlement_details`
- `staff_actual_transfers`
- `staff_transfer_allocations`

歷史資料唯讀保留，不刪除。能唯一證明的 legacy transfer 才可另案 backfill direct links；不能唯一證明者保持 legacy read-only 並投影 ambiguity anomaly。

既有部分付款或無法唯一還原的 allocation 不自動轉換。異常中心顯示舊交易、可能義務、差額與 recovery actions，由人員確認後呼叫 Staff Payables typed Preview／Apply 建立必要 adjustment／reversal／direct link；原 legacy rows 不覆寫。

Archive 在本輪預設永久保留且不提供自動刪除。存取權限治理仍依既定範圍暫緩，未來另立運維規格時不得回溯刪除既有檔案。

## 6. 驗收

- 同月嫂同月兩訂單：兩筆義務、一列匯出、一筆銀行支出完整連結兩筆。
- completed／anomaly 不匯出。
- 部分、超付、混 staff、帳戶不唯一零正式 payout。
- return／reversal 重開 payable。
- exact replay 不重複 event 或 links。
- 4 日、5 日多次下載各自保存；archive 與 response bytes 完全相同。
- archive failure 不回傳檔案。
- 完整履約後即使客戶爭議，月嫂完整義務不得因取消縮減。

## 7. Typed Commands／Results／Errors

Commands：

- `QueryStaffPayables`
- `PreviewStaffPayoutReconciliation`
- `ApplyStaffPayoutReconciliation`
- `PreviewStaffPayoutReturn`
- `ApplyStaffPayoutReturn`
- `PreviewStaffPayoutReversal`
- `ApplyStaffPayoutReversal`
- `ExportAccountsPayableWorkbook`
- `QueryAccountsPayableArchive`
- `QueryHistoricalStaffPayoutRepair`
- `PreviewHistoricalStaffPayoutRepair`
- `ApplyHistoricalStaffPayoutRepair`

Stable errors：

- `staff_payable_not_found`
- `invalid_staff_payout_intent`
- `outgoing_bank_fact_not_eligible`
- `staff_bank_account_ambiguous`
- `cross_staff_allocation_forbidden`
- `staff_payout_amount_mismatch`
- `staff_obligation_not_exactly_settled`
- `staff_payout_reversal_invalid`
- `staff_payable_candidate_stale`
- `accounts_payable_export_has_anomaly`
- `accounts_payable_archive_failed`
- `idempotency_conflict`
- `transaction_failed`
- `historical_staff_payout_not_eligible`
- `historical_staff_payout_obligation_binding_invalid`

## 8. Live writer 退出

- `services/staff_payment_transactions.py` 的相容交易規則遷移至 immutable payout ledger。
- `services/staff_actual_transfers.py` 與 `staff_transfer_allocations` 停止新增；可證明的
  legacy links 另案 backfill，無法證明者留異常。
- `services/staff_monthly_settlements.py` 停止建立新 header／detail，只保留歷史查詢。
- Finance Import 只送 typed outgoing intent，不得 UPDATE payout ledger 或 payable status。
- final writer scan 必須證明 payout／return／reversal events、obligation links 與 payable
  projection 只有 Staff Payables adapters 可寫；export 只能讀取且不得改付款狀態。
