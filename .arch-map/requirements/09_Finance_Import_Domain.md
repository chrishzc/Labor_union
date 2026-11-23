# Finance Import／Canonical Bank Facts Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Finance Import Domain（`domains/finance_import/`、`subsystems/finance_import/`）
- 單一負責範圍：銀行來源檔規格驗證與正規化、不可變 `finance_import_batches`／`finance_import_rows`／`finance_import_occurrences`／`finance_import_ingestion_attempts` 與 `finance_import_classification_events`、跨檔去重 fingerprint、銀行流水交易分類與 typed dispatch intent、Reprocess Preview／Apply、`finance_import_manual_review`、React 單鍵匯入 terminal receipt 及未核銷誤匯來源排除（`FI-DEC-001～003`）。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Staff Payables / Export Domain](05_Staff_Payables_Export_Domain.md)、[Anomalies Domain](06_Anomalies_Domain.md)、[Government Subsidy Domain](14_Government_Subsidy_Domain.md)、[Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)、[銀行流水對帳與手動補登](22_銀行流水匯入與帳務異常處理正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

| 概念 | 唯一權威 | 性質 |
|---|---|---|
| 來源檔識別 | content digest、logical name、format id、sheet identity | immutable ingestion fact |
| 匯入批次 | `finance_import_batches` | append-only lifecycle fact |
| 匯入嘗試稽核 | `finance_import_ingestion_attempts`（`FinanceImportAttempt`） | append-only out-of-transaction audit |
| canonical bank fact | `finance_import_rows` canonical raw columns | immutable root fact |
| 來源出現位置 | `finance_import_occurrences` | append-only occurrence |
| 去重身分 | versioned canonical fingerprint contract | deterministic identity |
| classification | `finance_import_classification_events` 之 current projection | derived, monotonic |
| reconciliation | owning Finance Domain 正式 ledger／allocation | cross-Domain root result |
| reprocess receipt | `finance_import_reprocess_runs` | append-only audit |

- **嚴格禁止覆寫**：canonical raw columns、`fingerprint + fingerprint_version`、occurrence、ledger reference、classification event 與 reprocess run 一律禁止 `UPDATE／DELETE`。主機絕對路徑僅為診斷資訊，不得進入公開 manifest；姓名、金額、列號、相似備註皆非 identity SSOT。
- **跨 Domain 分責**：Finance Import 不擁有客戶應收／退款、月嫂薪資／實付、政府期間核銷、Orders lifecycle 或 Alert workflow；Client Finance／Staff Payables／Government Subsidy 僅透過 ports 消費銀行事實與 typed intent。

### 2.1 四個正交狀態軸與重複來源邊界

1. **Batch lifecycle**：`staged → completed | failed`（失敗批次僅由主交易外之 `FinanceImportAttempt` 留存）。
2. **Occurrence outcome**：`inserted | skipped_existing`。
3. **Classification**：`pending → business classification | non_business_review`；歷史重分類僅允許符合資格者 `non_business_review → business classification`，不得自動倒退。
4. **Reconciliation**：唯一以 owning Domain 正式 ledger／allocation 為準（相容欄位 `pending → reconciled` 不作第二套 SSOT）；正式退匯／沖正／調整不將核銷軸改回 `pending`。

- **同批與跨批的重複交易**（判定方式見[銀行流水去重規則](22_銀行流水匯入與帳務異常處理正式規格.md#32-重複排除與去重規則bank-04)）：以銀行交易指紋判定是否為同一筆交易。同一交易在本批首次入庫時，只建立一筆銀行原始交易（canonical bank fact），保留同批各來源列位置（occurrence），重複列記為 `skipped_existing`。如果該交易已在先前批次入庫，本次只計入回執的重複筆數；不新增來源位置、分類或待核銷項目，也不改原交易的核銷狀態。
  - **同批例**：經辦匯入一份銀行明細，首次入庫的同一筆交易出現在第 17、18 列。核對匯入結果時，應只有一筆原始交易，保留兩個來源列位置，第 18 列記為重複。
  - **跨批例**：同一筆交易已在先前批次入庫並核銷，經辦匯入另一份也含該交易的明細。本次回執只增加一筆重複，不新增來源位置、分類或待核銷項目；原交易仍維持已核銷。

## 3. 公開契約與流程

### 3.1 Source Intake、正規化與匯入嘗試稽核

- Normalization 為純計算（無 DB 交易），嚴格驗證 UTF-8 與整數 TWD 金額（小數回傳 typed anomaly）。
- **欄位解析與辨識**：
  - **永豐（Sinopac）**：存入以 `bank_references["銷帳編號"]` 之 `99781699 + 6碼`（含 `A` 開頭非市民 `115501` 規則）為來源，嚴格遵守 [Client Finance 虛擬帳號三階段判定](04_Client_Finance_Domain.md#35-專屬虛擬帳號與單案修改99781699va-0106)，不使用姓名／金額備援或「存摺備註」；支出依 [備註六碼與案件範圍定位](22_銀行流水匯入與帳務異常處理正式規格.md#42-永豐備註六碼定位案件規則與非市民-a-案件) 僅讀原檔 `memo`（「備註」，絕不讀「存摺備註」）擷取連續 6 碼定位案件。一般退款以備註或正式人工配對驗證案件，退款帳號不參與辨識或核銷。
  - **台新（Taishin）與 Legacy**：台新政府入款與政府來源退回依「新竹市政府／市府」等政府來源標記；台新個人補助出款（`P台`／`R台`）與永豐出款四階段配對、`0～100` 元內扣手續費及方案候選辨識，一律遵循 [銀行明細判定與支出核銷契約](22_銀行流水匯入與帳務異常處理正式規格.md#outgoing-statement-fee-reconciliation) 與 [補助方案判定表](22A_案件帳務三方案與補助流向正式規格.md#subsidy-flow)。
- **新來源入庫與人工配對**：見[銀行流水匯入正式規格 §3.1](22_銀行流水匯入與帳務異常處理正式規格.md#31-成功明細資格bank-01bank-02)。
- **同案多筆補款防誤判**：同一案件多筆不同銀行列各自實付不同時，保留各筆並合計供核銷，禁止只因命中同一期款或單筆不等於應收而標為 `suspected_duplicate_business_match`；若多筆各自足額指向同一期款，則轉合計超收人工核對。
  - **同一期款補款例**：一期應收 NT$1,000。經辦匯入兩筆已定位到本案同一期的不同銀行交易，分別實付 NT$400 與 NT$600；核對時保留兩筆，合計 NT$1,000 供核銷，不因同一期或單筆金額不等於應收而標為重複。若兩筆都實付 NT$1,000，則將合計超收轉人工核對。
- **`FinanceImportAttempt`**：在主 Apply 交易外記錄 command identity、digest、phase、typed error、起迄時間與 outcome（不記完整帳號、姓名或 raw row）；exact retry 直接重播原 attempt／receipt。

### 3.2 Business Dispatch 與 Historical Reprocess

- **Typed Dispatch Ports**：`ClientReceiptReconciliationPort`、`ClientSubsidyReturnReconciliationPort`、`GovernmentSubsidyReceiptPort`、`StaffPayoutReconciliationPort`、`StaffActualTransferPort`、`FinancePendingOccurrencePort`、`OrderDepositLifecycleIntentPort`。
- owning Domain 回傳 `reconciled | existing | pending | rejected | conflict`；訂金核銷只送出 Orders typed intent，不得直接修改 `orders.status`；`government_subsidy` 固定委派 `GovernmentSubsidyReceiptPort`。
- **Historical Reprocess Preview／Apply**：限定單一 completed batch 之 `non_business_review + pending` 列；Preview 零寫入並回傳 deterministic `plan_fingerprint`；Apply 鎖定驗證 fingerprint、expected batch version 與 idempotency key，於單一 outer UoW 原子寫入 append-only `finance_import_classification_events` 與 `finance_import_reprocess_runs`。

### 3.3 正常匯入邊界（`FI-DEC-001～003`）與 React 單鍵匯入

- **`FI-DEC-001`（Preview 與稽核）**：File Watcher 偵測 `downloads/bank/*.xlsx` 後僅負責驗證穩定檔案並觸發受控匯入指令，禁止直接連 DB 或修改業務投影。Preview 須列出新增數、重複數、預計 dispatch 類型與整數金額、待分類／`business_pending`／blocked 數、判定證據與 `plan_fingerprint`。
- **`FI-DEC-002`（修改分流）**：禁止直接編輯 canonical row。未核銷的誤匯流水，由具權限的系統管理員填寫原因，依[銀行流水規格 §3.2](22_銀行流水匯入與帳務異常處理正式規格.md#32-重複排除與去重規則bank-04)排除；保留原始列與指紋，不再列為待核對、重配或核銷。正確來源依正常流程匯入；主檔缺漏回 owning Domain 補齊再重預覽；分類歧義經 Correction Workbench 補 `evidence`（必填）與 `reason`（選填）；已入帳錯配回 owning Domain 走 `reversal／adjustment／refund`。
- **`FI-DEC-003`（整批與合格候選範圍）**：通過驗證之 candidates 一次 Apply；`non_business_review` 與 `business_pending` 留待處理；integrity／collision／stale／formal conflict 阻擋整批 Apply。客戶補助退款預檢於 Preview 階段即檢查擬建／沿用退款與接續核銷資格（缺資金／墊款資格轉 `business_pending` 並明確標示，不阻擋同批其他合法款）。禁止未經稽核的勾選略過機制。
- **React 單鍵匯入 Terminal Receipt**：使用者選檔後直接點擊一次「匯入銀行交易明細」，畫面不提供入帳原因欄。系統依序執行 `Upload/Ingest → 內部 Preview → 符合 apply_allowed 且有候選時自動 Durable Apply → terminal receipt`。受理 `202 Accepted` 非完成態；僅當 batch job `succeeded` 且從 `finance_import_apply_receipts` 讀回 `resulting_batch_version`、`reconciled_count`、`existing_count`、`pending_count` 後始可顯示入帳完成；結果未明以原鍵重查。

### 3.4 匯入檢核與業務人工核對

- **`finance_import_manual_review`**：綁定唯一 canonical bank fact（`source_id = <finance_import_row_id>`），呈現遮蔽帳號、分類與核對候選；`CorrectAndPostFinanceImportRow` 於單一 outer UoW 鎖定 row、review 與 target obligations，寫入 manual classification event、owning ledger／allocation、reconciliation receipt 及 outbox；任何一步失敗全批回滾。若已有相符的舊警示，可追加解除紀錄，不新建警示。已有 Client Finance 正式 receipt 之列一律自待確認清單排除。
- **來源檢核與歷史邊界**：來源格式問題由 Finance Import 保存並在該批的來源檢核結果讀回，和待人工配對或確認的業務明細分開。`IMPORT-006` 已退役，不再產生批次警示，也不提供舊異常更正工作台；歷史核對與驗證邊界見 [Anomalies Domain](06_Anomalies_Domain.md) §3.3。

### 3.5 Typed Commands、Errors、交易與 Live Writer Exit

- **Commands**：`NormalizeFinanceWorkbook`、`PreviewFinanceImport`、`ApplyFinanceImport`、`PreviewFinanceReprocess`、`ApplyFinanceReprocess`、`PreviewFinanceImportCorrection`、`ApplyFinanceImportCorrection`、`CorrectAndPostFinanceImportRow`、`QueryFinanceImportBatch`、`QueryFinanceImportRun`。
- **Stable Errors**：`invalid_source_file`、`unsupported_bank_format`、`invalid_canonical_row`、`strict_decode_failed`、`batch_not_found`、`batch_not_completed`、`batch_too_large`、`stale_preview`、`idempotency_conflict`、`classification_conflict`、`manual_evidence_required`、`reconciliation_invariant_violation`、`dispatch_rejected`、`downstream_unavailable`、`transaction_failed`。僅 `downstream_unavailable`／deadlock／transient storage error 得依原 idempotency key 做 bounded retry。
- **交易模型**：Normalization 無交易；Preview 零寫入；Apply／Reprocess／Correction 於單一 outer UoW 提交；Outbox 在正式交易提交後處理，其派送不回滾已提交的銀行事實。Query 永遠唯讀（整庫明細匯出規範見 [銀行成功明細整庫匯出](22_銀行流水匯入與帳務異常處理正式規格.md#33-成功明細整庫匯出bank-03)）。
- **Writer Exit**：runtime 僅保留 `domains/finance_import/` 與 `subsystems/finance_import/`；不得重新建立 `services/finance_cancellation_code.py`、`services/finance_import_states.py`、`services/finance_import_dispatch.py` 等相容路徑，File Watcher 亦嚴禁直連 DB 或自寫 Alert。

## 4. 驗收標準

1. Unit／Module 驗證 Legacy、Sinopac、Taishin 原生格式解析、deterministic fingerprint、分類詞彙、plan fingerprint 與 typed error mapping 正確無缺。
2. Subsystem 驗證同批重複留 `1` canonical ＋ 多 occurrences、跨批重複僅計 receipt 數而不重複建待核銷成員、dry-run 零寫入、reprocess exact replay 與 stale 拒絕。
3. Global E2E（real-format XLSX ＋ isolated MySQL）驗證 Finance Import → Client Finance（三階段收款、多筆補款合計、取消補退）／Staff Payables（0～100 元手續費、P永/P台）／Government Subsidy／Orders 訂金推進／React terminal receipt 與全批失敗原子回滾。
