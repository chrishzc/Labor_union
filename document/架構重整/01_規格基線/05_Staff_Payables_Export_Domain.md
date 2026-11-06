# Staff Payables／Accounts Payable Export

> 2026-11-05人工方案交接已核准：依[16 §2.5.5](16_Staff_Payables與Client_Refund正式規格.md#manual-subsidy-plan-payables-handoff-20261105)，原正式服務結束後以最後正式保存的人工方案承接補助歸屬；歷史自動分類只比對，不因未知自動否定人選安排。與既有義務或真實收付款衝突僅將受影響款項待確認，其他合法到期款照原規則；更正走原owner，原流水／核銷／日期及已匯出Excel保留。保存方案不建立應付或付款；後續已依明確實作授權完成下游交接及限定驗收，詳16 §2.5.5與既有工作包。原「本輪只更新規格」階段已取代，僅供歷史追溯。

> 2026-11-05 最新裁決：全額免自備依 [`22` §17.4.1](22_銀行流水匯入與帳務異常處理正式規格.md#full-subsidy-no-advance-20261105)；補助轉交月嫂清償原應收，不增加薪資。會計Excel契約沿規格16 §2.5.4 APX-SOURCE-01～READONLY-07：月嫂永豐／台新出款分列、只列正式餘額，姓名欄顯示公會自訂編號＋姓名。既有付款及日期保留，會計Excel已完成的限定修正與未完成的資料補登邊界見原帳務工作包，案件抽屜／人工保存結果見22 §18.10。**已取代，僅供歷史追溯**：原「本次只改文件」為文件階段，不表示後續限定實作未發生；本輪清理不重跑或擴大驗收。

> 2026-11-03 三方案與銀行核銷最新裁決：依 [`22` §17](22_銀行流水匯入與帳務異常處理正式規格.md#case-accounting-schemes-20261103)，月嫂應收合計等於案件總額，月嫂實收 P＝永豐一般付款 P永＋台新補助轉交 P台；P台 是同案應付的一部分，不得額外加付或另計一次薪資。歷史自動辨識除22 §17.4.1免自備例外外須客戶需繳各期已齊；進行中人工補助安排依22 §18可提前保存，不重算期款或既成應付，案件結束後的補助及應付仍沿原owner承接；月嫂核銷仍須逐筆真實交易、正確案件與對象；分類或工會差額為零不能代替付款證據。舊文由身分直接推先墊／全補助流向的部分由新契約取代；歷史義務、期程、清冊與付款不因此改寫。**已取代，僅供歷史追溯**：原「本次僅規格，未修改程式或匯出」只描述2026-11-03文件階段；後續限定實作依上方來源分列，人工安排與應付交接已核准依16 §2.5.5：人工方案決定新流程的補助歸屬，原金融owner負責款項成立／更正／核銷，清冊只讀正式餘額；後續交接實作及驗收以16 §2.5.5與既有工作包當次結果為準。**已取代，僅供歷史追溯**：先前交接細節待確認的狀態。政府補助清單統一方案三格式不等於改動本 Domain 的會計應付清冊格式。

> 2026-11-02 差額認列、人工金額更正與政府整期差額的最新實作／驗證見 [規格22 §16.9.1](22_銀行流水匯入與帳務異常處理正式規格.md#accounting-differences-implementation-20261102)。本檔 2026-11-01 的「尚未實作／本次僅規格」為當時記錄，以該續作結果為目前狀態；bank／ledger／allocation 的不可變性與各 owner 歸屬不變。

> 2026-11-01 最新差額流程見 [`22` §16](22_銀行流水匯入與帳務異常處理正式規格.md#finance-differences-20261101)、Payroll `03` §0 與 Client Finance `04` §0.2；本次只更新規格，不改程式或帳務。

- 月嫂原應付有誤，由 Payroll 人工結果金額更正承接；不足額／超付仍保留實付與待付餘額／追償。Staff Payables 不旁路改 Payroll 金額或銀行事實。
- 歷史原因已確認無法查明的案件人工核銷，只作案件標記並排除實際金額統計，不等同既有 `paid／settled` 付款事實或義務處分，不直接計工會損益。
- 本次移除退匯功能；下述 return／reversal 根事實及淨實付計算保留歷史證據用途，不表示新增退匯操作。原 API／writer 實際移除未獲本次施工授權。

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
| due date | 原 owner 正式義務及資金來源分期期程；既有 `staff_payment_due_date`／各期 due date 保留，不由身分、全補助分類或政府實際入款重推 |
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

Staff Payables 讀取 Payroll 的正式應付與 assignment 歸屬，案件月嫂應收合計等於案件總額。永豐 P永、台新 P台 與各筆部分付款可清償同一應收，不能因補助來源另加薪資或禁止分次付款；真實實付不足仍保留剩餘款，超付另循原追償。客戶 R永／R台 屬 Client Finance，不清償月嫂款。

**已取代，僅供歷史追溯**：原由一般／非全補助／全補助身分推定客戶先墊與單一月嫂付款日的規則，不再決定新三方案。原次月／第二月 15 日等已形成到期日、清冊、義務、實付及沖正證據保留，不批次移期或重算。

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

規格 `27` 的「歷史訂單－帳務完成」只消費本 Domain 對原應付及有效更正的正式結清結果。各月嫂應結清款項的餘額均須為 0，且無應付來源、付款、退匯／沖正或核銷關聯疑義。缺正式應付或付款證據時列待確認。未列入清冊的查核及補登／更正入口依[規格 16](16_Staff_Payables與Client_Refund正式規格.md#historical-payables-review-entry)。

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
→ 同月同月嫂多訂單僅在付款日、出款銀行及收款帳戶相同時合併（永豐／台新分列）
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

- 同月嫂同月兩訂單且付款日／出款銀行／收款帳戶相同：兩筆義務、一列匯出、一筆銀行支出完整連結兩筆；永豐一般款與台新補助款分列，沿規格16 APX-A01～09驗收。
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
