# Staff Payables／Accounts Payable Export Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Staff Payables Domain（`domains/staff_payables/`）、Accounts Payable Export Subsystem（`subsystems/staff_payables/`）
- 單一負責範圍：月嫂付款義務（`staff_obligations` 消費）、不可變實付／退匯／沖正帳本（`staff_payout_events`、`staff_payout_obligation_links`）、`payable／partially_paid／completed／anomaly` 狀態機、Historical `paid | settled` 月嫂付款證據、Payable Anomaly 投影與 Accounts Payable Export 封存不變量。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Payroll Domain](03_Payroll_Domain.md)、[Finance Import Domain](09_Finance_Import_Domain.md)、[Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)、[Accounts Payable Export 與現金需求清冊](16A_Accounts_Payable_Export與現金需求清冊規格.md)、[銀行流水對帳與手動補登](22_銀行流水匯入與帳務異常處理正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

| 概念 | 唯一權威 |
|---|---|
| 原始銀行支出 | Finance Import `CanonicalOutgoingBankFactPort` |
| 月嫂付款義務 | [Payroll Domain](03_Payroll_Domain.md) 產生的 immutable obligation events 與 `staff_obligations` current projection（`staff_payments` 僅唯讀相容投影） |
| payout／return／reversal | immutable Staff Payout Ledger（`staff_payout_events`、`staff_payout_obligation_links`） |
| 銀行帳戶 owner | 唯一有效 primary `staff_bank_accounts` |
| net paid | `succeeded payout - return - reversal`（含經合法認列之收款方內扣手續費清償額） |
| balance | `obligation - net_paid` |
| due date | 原 Payroll／Orders 正式義務及資金來源分期期程；已形成之 `staff_payment_due_date` 保留，不因政府入款時間或方案重推 |
| 同月合併 | Query／export read projection，不落庫合併 entity |

### 2.1 狀態機與結清守恆

```text
balance == obligation 且 net_paid == 0       → payable
balance == 0                                  → completed
0 < net_paid < obligation                     → partially_paid（餘額繼續待付）
超付、ownership／帳戶／金額衝突               → anomaly
return／reversal                              → 依剩餘有效淨實付重開 payable／partially_paid
```

- 月嫂義務可由永豐一般出款（`P永`）、台新補助轉交（`P台`）及多次部分付款合計清償，合計不得超出案件總額 `T`；補助來源不額外增加薪資權利。
- `R永`／`R台` 屬於 [Client Finance](04_Client_Finance_Domain.md)，不得用以清償月嫂應付。
- 一般核銷依 [銀行流水對帳規則](22_銀行流水匯入與帳務異常處理正式規格.md#outgoing-statement-fee-reconciliation) 處理 `0 <= (應付 - 實付) <= 100` 內扣手續費並直接結清；超過 100 元之不足額保留原應付與實付差額繼續待付，超付轉入追償（`staff_overpayment_recovery`），詳細操作流程見 [Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)。

### 2.2 Payout Ledger 資料模型

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

- 正式 ledger 僅寫入實際成功的 `payout | return | reversal`；失敗或未明嘗試停留在 Finance Import staging／異常。每筆成功銀行支出須完整分配至所選義務。

## 3. 公開契約與流程

### 3.1 Payable Query 與 LINE 自助查詢

- Query 選取有效 obligations，依 `staff_id + target payment month` 聚合顯示，同時保留逐筆 `staff_payment_ids`、case numbers 與金額。
- 月嫂 LINE 自助查詢讀取正式 projection 的應付、實付淨額與剩餘待付；部分付款且有餘額回傳 `partially_paid`（「部分付款」）。薪資結算與付款成功均不發送 LINE 通知。

### 3.2 Payout Preview 與 Apply

- **Preview（零寫入）**：驗證所有銀行列為 outgoing debit、同一月嫂且無重複 raw fact。永豐及其他帳號路徑要求帳戶 owner 唯一；台新 `P台` 依 [台新辨識契約](22_銀行流水匯入與帳務異常處理正式規格.md#43-台新補助出款備註辨識taishin-memo-0105) 重新讀取原始備註月嫂姓名唯一確認月嫂，不要求交易收款帳號或主要帳戶，且姓名須與所選義務一致。
- **Apply（單一 outer UoW）**：fresh-read 來源、銀行事實、義務及版本，寫入 `staff_payout_events`、`staff_payout_obligation_links`、狀態投影與 outbox；重送 same-key 回傳原收據，絕不重複配對或修改原應付金額。

### 3.3 Historical Payout Evidence／Settlement

- 使用系統前且已正式採納的歷史訂單，首要證據仍為 Finance Import canonical outgoing bank fact。唯舊銀行／帳務證據缺失、歸屬不明或無法可靠還原時，方允許歷史人工 `paid | settled` Query／Preview／Apply。
- Apply 必須綁定 exact `case_no`、`staff_id`、`payer=工會`、`payee=月嫂`、所選 obligations 與 historical adoption，並保存 `actor`、`reason`、`evidence`、`expected_version`、`fingerprint`、`idempotency_key`、`receipt` 與 `outbox`；付款日不明時記錄 `unknown`，禁止偽填日期或偽造 bank row。
- 歷史 `paid` 只建立選定月嫂義務付款事實；`settled` 僅終止本 Domain 選定義務，不影響 Client Finance。客戶付款、Orders 完成、清冊下載或政府撥款均不能推定月嫂已付款。未入清冊查核與補登見 [Accounts Payable Export 規格](16A_Accounts_Payable_Export與現金需求清冊規格.md#historical-payables-review-entry) 與 [歷史訂單帳務規格](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

### 3.4 Payable Anomaly Facts 與 Accounts Payable Export 不變量

- Anomaly 投影輸出：`PAYOUT-001`（到期未匯）、`PAYOUT-002`（應付於原基準日後始形成或變動）、`PAYOUT-003`（銀行主檔不完整）及 ownership／共享帳戶／金額衝突。人工 resolve 警示僅記錄處置，不變更義務或實付。
- **Accounts Payable Export（唯讀快照管道）**：
  ```text
  一致性 read transaction 讀取當下 payable
  → 排除 completed 與 anomaly
  → 同月同月嫂僅於付款日、出款銀行（永豐／台新分列）與收款帳戶皆相同時合併
  → 驗證帳戶、整數金額、付款日與來源
  → 產生一次 XLSX bytes → 計算 SHA-256
  → 原子寫入 downloads/accounts_payable_archive/YYYY/
  → 驗證 archive hash 一致後回傳完全相同 bytes
  ```
- 檔名含目標付款日、產生時間與 short hash，永不覆蓋；archive 失敗即阻擋下載，下載本身不改寫付款狀態。詳細 Excel 欄位與現金需求清冊契約由 [Accounts Payable Export 與現金需求清冊](16A_Accounts_Payable_Export與現金需求清冊規格.md) 擁有。

### 3.5 Typed Commands、Errors 與 Legacy Exit

- **Commands**：`QueryStaffPayables`、`PreviewStaffPayoutReconciliation`、`ApplyStaffPayoutReconciliation`、`PreviewStaffPayoutReturn`、`ApplyStaffPayoutReturn`、`PreviewStaffPayoutReversal`、`ApplyStaffPayoutReversal`、`ExportAccountsPayableWorkbook`、`QueryAccountsPayableArchive`、`QueryHistoricalStaffPayoutRepair`、`PreviewHistoricalStaffPayoutRepair`、`ApplyHistoricalStaffPayoutRepair`。
- **Stable Errors**：`staff_payable_not_found`、`invalid_staff_payout_intent`、`outgoing_bank_fact_not_eligible`、`staff_bank_account_ambiguous`、`staff_memo_recipient_unconfirmed`、`cross_staff_allocation_forbidden`、`staff_payout_amount_mismatch`、`staff_obligation_not_exactly_settled`、`staff_payout_reversal_invalid`、`staff_payable_candidate_stale`、`accounts_payable_export_has_anomaly`、`accounts_payable_archive_failed`、`idempotency_conflict`、`transaction_failed`、`historical_staff_payout_not_eligible`、`historical_staff_payout_obligation_binding_invalid`。
- **Legacy Exit & Writer Boundary**：新架構停止依賴 `staff_monthly_settlements`、`staff_monthly_settlement_details`、`staff_actual_transfers`、`staff_transfer_allocations`（唯讀保留不刪除）；僅能唯一證明之歷史轉帳可另案 backfill direct links，無法證明者維持 anomaly 交人工處理。`services/staff_payment_transactions.py`、`services/staff_actual_transfers.py`、`services/staff_monthly_settlements.py` 與 Finance Import 均不得直接寫入或 `UPDATE` payout ledger／payable status。

## 4. 驗收標準

1. 同月嫂同月兩筆訂單且付款日、出款銀行、收款帳戶一致時：維持兩筆獨立義務、匯出為一列合併，且單筆銀行支出可完整分配至兩筆；永豐一般款與台新補助款分開呈列。
2. `completed` 與 `anomaly` 義務不進入 AP 匯出；`return`／`reversal`（僅限歷史證據或已允許之有效沖正路徑）可重開 `payable`。
3. 混用不同月嫂或對象不唯一時拒絕建立 payout；台新 `P台` 僅需原始備註姓名唯一且同人即不阻擋缺帳號；0～100 元轉帳手續費依對帳規則結清。
4. 同日多次匯出各自保留不可變檔案，archive bytes 與 HTTP response bytes 完全一致；archive 失敗時絕不回傳半份檔案。
5. 完整履約之月嫂義務不因後續客戶爭議或取消而被縮減；same-key 重送不重複建立事件或 links。
