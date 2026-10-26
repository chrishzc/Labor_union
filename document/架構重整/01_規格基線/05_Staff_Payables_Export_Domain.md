# Staff Payables／Accounts Payable Export

## 1. 分責

`Staff Payables` 管理月嫂付款義務、銀行出款、退匯／reversal、核銷及 payable／partially_paid／completed／anomaly 投影。

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
| due date | Orders 唯一 `staff_payment_due_date`：一般及非全補助案件為結案後次一曆月 15 日；社福、有效正式服務不超過 120 小時且客戶應付為 0 的全補助案件為結案後第二曆月 15 日 |
| 同月合併 | Query／export projection |

狀態：

```text
balance = obligation 且 net_paid = 0 → payable
balance = 0 → completed
0 < net_paid < obligation → partially_paid，餘額繼續待付
超付、ownership／帳戶／金額不符 → anomaly
退匯／reversal → 依剩餘有效付款重算 payable／partially_paid
```

不足額核銷保留原應付全額，只記錄實際銀行付款；補款僅核銷當下剩餘款。

Staff Payables 對每一 assignment 只接收 Payroll 的一筆整筆應付，不因補助來源拆成補助薪資／自費薪資等多筆義務。非全補助的補助市民訂單由客戶先代墊完整服務薪資，月嫂整筆應付日為結案後次一曆月 15 日；服務完成後退還客戶的補助款屬 Client Finance，不能改寫或清償月嫂義務。全補助案件固定為社福、有效正式服務不超過 120 小時且客戶應付為 0，客戶不出資，月嫂整筆應付日為結案後第二曆月 15 日；實務申請通常排滿 120 小時。政府款未入帳不改變原整筆應付及到期日；若實際付款不足，先核銷實付，剩餘款繼續列待付。

## 3. Subsystems

### Payable Query

選取有效 obligations，依 `staff_id + target payment month` 聚合顯示，但保留所有 `staff_payment_ids`、case numbers 與逐筆金額。聚合不落 DB entity。

月嫂 LINE 自助查詢依本人及目標付款月份，讀取正式 projection 的應付、實付淨額及剩餘待付金額。已付部分且仍有餘額時回傳 `partially_paid`，畫面顯示「部分付款」；未付、付清及異常分別保留原狀態。補款、退匯或沖正後重新查詢即反映目前帳務，不由 LINE 重算或改寫。薪資結算及付款成功均不發送 LINE 通知。

### Payout Reconciliation Preview

驗證所有銀行列為 outgoing debit、同一月嫂、帳戶 owner 唯一，且無重複 raw fact。一般核銷的支出總額須恰等於所選義務的當下剩餘款。付款不足走不足額核銷，先記實付並保留餘額；付款超額走超額核銷，另列追收。不得跨 staff、重用已核銷銀行列或改寫原應付。

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

正式 ledger 只保存實際成功的 payout／return／reversal；失敗嘗試留在 bank staging／anomaly，不混入正式帳本。每筆成功銀行支出須完整分配；不足額核銷允許 obligation 留有未付餘額。

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
- 一般足額核銷拒絕不足／超額；專用差額核銷依規格 16 保存實付、待付餘額或超額追償。混 staff、帳戶不唯一不得建立正式 payout。
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
