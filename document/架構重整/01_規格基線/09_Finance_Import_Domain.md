# Finance Import／Canonical Bank Facts Domain

## 1. Domain 責任

Finance Import 是銀行來源檔、canonical bank facts、occurrence、分類結果及歷史重分類稽核的唯一 owner。

它負責：

- 驗證來源檔格式並轉成 canonical normalized rows；
- 建立不可變 batch、canonical row 與 occurrence；
- 以穩定 fingerprint 跨檔去重；
- 依明確證據分類銀行流水；
- 將可處理的業務分類轉成 typed dispatch intent；
- 提供正常匯入、dry-run、歷史重處理、exact replay 與查詢；
- 產生 bounded import-review desired state 供 Anomalies 投影。

它不擁有：

- 客戶應收、退款或補助退還義務；
- 月嫂薪資、付款義務或正式 payout；
- 政府補助申請、核准、撥款、退匯或 allocation；
- Orders lifecycle 或服務狀態；
- Alert workflow；
- 人員、客戶或訂單主檔；
- preserve-data database cutover。

Client Finance、Staff Payables 與 Government Subsidy 只能透過 Finance Import ports
讀取銀行 facts 或接收 typed dispatch intent，不得直接解析 Excel、修改 canonical row、
共用 Finance Import repository 或自行推測分類。

## 2. SSOT 與資料權威

| 概念 | 唯一權威 | 性質 |
|---|---|---|
| 來源檔識別 | content digest、logical name、format id、sheet identity | immutable ingestion fact |
| 匯入批次 | `finance_import_batches` | append-only lifecycle fact |
| canonical bank fact | `finance_import_rows` 的 canonical raw columns | immutable root fact |
| 來源出現位置 | `finance_import_occurrences` | append-only occurrence |
| 去重身分 | versioned canonical fingerprint contract | deterministic identity |
| classification | append-only classification decision event 的 current projection | derived, monotonic |
| reconciliation | owning Finance Domain 的正式 ledger／allocation | cross-Domain root result |
| reprocess receipt | `finance_import_reprocess_runs` | append-only audit |
| reclassification audit | `finance_import_reclassification_events` | append-only event |
| import-review alert | Anomalies current projection | rebuildable derived state |

Canonical raw columns、`fingerprint + fingerprint_version`、既有 occurrence、正式 ledger
reference、classification event、reprocess run 及 event 禁止 UPDATE／DELETE。若銀行
adapter 契約需要改變會影響 fingerprint，必須另立 versioned fingerprint migration；
不得原地改寫舊 row。

主機絕對路徑只屬 adapter 診斷資訊，不是 source identity，也不得進入公開 manifest。

姓名、部分帳號、相同金額、Excel 列號、備註相似或人工猜測都不是 identity SSOT。

## 3. 五個正交狀態軸

Finance Import 不使用單一巨大狀態欄位：

1. Batch lifecycle：`staged → completed | failed`。
2. Occurrence outcome：`inserted | skipped_existing`。
3. Classification：
   - `pending → business classification | non_business_review`
   - 歷史重分類只允許 eligible
     `non_business_review → business classification`
   - 已是 business classification 不得自動倒退。
4. Reconciliation：由 owning Finance Domain ledger／allocation 推導；相容 projection
   可顯示 `pending → reconciled`，但不是第二套 SSOT，也不得倒退。
5. Alert lifecycle：`open → claimed → resolved`，問題重現可 reopen。

Occurrence outcome 不得寫入 classification 或 reconciliation。正式退匯、退款、adjustment 與 reversal 是 owning Finance Domain 的 append-only ledger event，不把 Finance Import reconciliation 改回 pending。

## 4. Subsystems

### 4.1 Source Intake／Normalization

將一份明確來源檔轉成 canonical input，不開啟 transaction、不讀業務資料庫、不建立正式帳務。

Modules：

- `FinanceSourceFileIdentity`
- `FinanceWorkbookFormatDetector`
- `LegacyBankStatementAdapter`
- `SinopacBankStatementAdapter`
- `TaishinBankStatementAdapter`
- `CanonicalBankRowNormalizer`
- `CanonicalBankRowValidator`
- `FinanceTransactionFingerprint`
- `FinanceFingerprintVersionPolicy`
- `NormalizationManifestBuilder`

不變量：

- strict UTF-8／型別驗證失敗時不產生部分 normalized result；
- 支援的 TWD 流水金額必須是整數；小數金額回 typed anomaly，不進正式核銷；
- fingerprint 只使用 versioned canonical fields；
- 合法虛擬帳號固定為 `99781699` 加六碼數字；
- Legacy 只讀 canonical cancellation code；
- Sinopac 只有 canonical value 缺失或不合法時，才可精確 fallback 至既有 raw bank reference；
- fallback 不回寫 canonical raw fact。

### 4.2 Canonical Staging／Occurrence

在一個 outer Unit of Work 內先保存銀行根事實，再分類與 dispatch。

Modules：

- `FinanceImportBatchRepository`
- `CanonicalBankFactRepository`
- `FinanceImportOccurrenceRepository`
- `FinanceImportFingerprintRepository`
- `CanonicalFactCollisionComparator`
- `DuplicateOccurrenceDetector`
- `FinanceImportBatchLifecycle`

不變量：

- 每一個可解析來源列都要有 occurrence；
- fingerprint 首次出現建立一筆 canonical row；
- 同檔或跨檔重複只新增 occurrence，結果為 `skipped_existing`；
- 重複 occurrence 不覆寫既有 classification、reconciliation 或人工處理結果；
- fingerprint 相同但非 fingerprint canonical facts 不一致時，保留 occurrence並回傳
  collision anomaly；不得靜默捨棄差異；
- 同批完全重複只允許首次 canonical insertion 進入下游；
- 任一 staging、classification 或 dispatch failure 使整批 Apply rollback。

`failed` batch 若需要在 transaction rollback 後保留，必須由獨立 ingestion-attempt audit 記錄；不得宣稱已 rollback 的 batch row 同時持久存在。此 audit model 尚未建立前，失敗以 typed result、操作 log 與 Anomalies intent 表示。

目標採用 append-only `FinanceImportAttempt`：

- 在主 Apply transaction 外保存 command identity、source content digest、phase、typed error、
  started／completed time 與 transaction outcome；
- 不保存 raw row、完整帳號、姓名或 credential；
- 成功時連結 completed batch；失敗時不偽造 batch id；
- exact retry 以 command id 與 canonical payload 回原 attempt／receipt。

### 4.3 Classification

Modules：

- `FinanceCancellationCodeProjection`
- `FinanceIdentityMapLoader`
- `FinanceTransactionClassifier`
- `FinanceClassificationTransitionPolicy`
- `ClassificationReasonCanonicalizer`
- `FinanceClassificationTuple`
- `ClassificationDecisionFingerprint`
- `ClassificationDecisionEventRepository`

分類先建立可重播、可解釋的候選，再決定可否提出 typed intent。候選可使用：

- canonical direction、amount、date、time、bank format；
- 完整 cancellation code；
- 唯一有效、完整且精確匹配的帳戶 ownership；
- 客戶／對方姓名、備註、對方帳號、金額與交易時間的正規化交叉證據；
- 已確認的銀行格式規則。

候選評分與行為：

1. 虛擬帳號、完整銀行 reference 或唯一帳戶 ownership 為強證據，直接建立候選。
2. 缺少強證據時，使用姓名、備註、對方帳號與金額產生排序候選；交易日期／時間保留在
   canonical fact 與 fingerprint，作為疑似重匯與人工覆核的時間證據。把日期／時間納入
   candidate score 的正式 owner-fact contract 尚未完成，不得假稱目前已用時間自動配對。
   每一個已採用的命中或未命中都進 `evidence`，並隨
   `classifier_version`／`decision_facts_fingerprint` 留存，讓 historical reprocess 可重播。
3. 單一候選且證據不衝突時，可形成 business classification 與 typed dispatch intent；
   owning Domain 仍須用 fresh obligations／ledger 做 Preview／Apply，不得因 classifier
   命中就直接寫正式帳務。
4. 零候選、多候選、跨 owner、證據衝突，或不同銀行列已命中同一義務時，改為
   `review_required`。第二筆疑似重匯不得靜默略過或自動打平，必須保留 canonical row
   並形成可處理的 anomaly。

### 4.3.1 真實銀行資料驗證註記

上述候選辨識規則是正式目標，但目前工作區沒有可再次隔離使用的真實對帳單樣本，故不得
把 pure／fixture test 當成辨識率或誤配率證明。`019fb603-937a-7e92-b8a2-a4e2838362d6`
的既有真實匯入紀錄只證明當時的虛擬帳號 classifier 覆蓋不足，不能用來宣稱新候選規則
已通過。

待取得可使用的真實格式 Excel 後，必須在 disposable MySQL 驗證：

- 強識別命中、姓名／備註／帳號／金額／時間的單一候選，以及零／多候選；
- 相同客戶不同日期的第二筆匯款，保留為疑似重匯而非自動打平；
- 正確率、錯誤候選率、人工覆核率與可重播的 evidence；
- intake → classification → Preview → Apply → owning Domain → Anomalies 的全鏈路。

分類結果必須包含：

- `classification_type`
- `classification_reason`
- `matched_identity_ids`
- `resolved_counterparty_account`
- `classifier_version`
- `decision_facts_fingerprint`

零個、多個或跨 owner 的**最終候選**一律 `non_business_review`。姓名、備註、帳號、金額、
日期／時間可以共同形成候選，但任何單一弱證據不得單獨取代 case／ledger identity。
初次分類與歷史重分類都必須 append decision event；current classification columns
只作相容 projection。

### 4.4 Business Dispatch Coordination

Finance Import 只決定「這筆銀行 fact 可提出哪種 typed intent」，正式義務、allocation、ledger 與業務狀態仍由 owning Domain 決定。

輸出 ports：

- `ClientReceiptReconciliationPort`
- `ClientSubsidyReturnReconciliationPort`
- `GovernmentSubsidyReceiptPort`
- `StaffPayoutReconciliationPort`
- `StaffActualTransferPort`
- `FinancePendingOccurrencePort`
- `OrderDepositLifecycleIntentPort`

流程：

```text
canonical bank fact
→ classification
→ typed dispatch intent
→ owning Domain fresh candidate
→ owning Domain validation
→ outer Unit of Work persistence
→ reconciliation result
→ transactional outbox
```

Owning Domain 可回傳：

- `reconciled`
- `existing`
- `pending`
- `rejected`
- typed `conflict`

`pending` 可以保留已完成的 business classification，但不得建立不完整 ledger。訂金核銷成功只能送出 Orders typed lifecycle intent；Finance Import 或 Client Finance writer 不得直接指定 `orders.status`。

`government_subsidy` 固定委派 `GovernmentSubsidyReceiptPort`；不得映射為 Client Finance。
Government Subsidy Domain 鎖定正式 claim batch／items，決定 receipt allocation、
reversal、outstanding 與 review。無唯一批次或 allocation 時回
`government_subsidy_review_required`，Finance Import 只保存 classification 與 review
intent，不建立政府 ledger。

### 4.5 Historical Reprocess Preview／Apply

選取條件：

- 明確單一 completed `batch_id`；
- 以 occurrence 決定成員，再對 canonical row id 去重；
- classification 為 `non_business_review`；
- reconciliation 為 `pending`；
- distinct rows 不超過預設 safety ceiling；
- row id 升冪鎖定，鎖後再次驗證。

Modules：

- `FinanceReprocessEligibilityPolicy`
- `FinanceReprocessBatchLoader`
- `CanonicalRowRehydrator`
- `FinanceReprocessCandidateBuilder`
- `FinanceReprocessPlanFingerprint`
- `FinanceReprocessReplayValidator`
- `FinanceReprocessRunRepository`
- `FinanceReclassificationEventRepository`
- `FinanceReprocessResultBuilder`

Preview：

- 執行與 Apply 相同的 rehydrate、classification、dispatch candidate 與 desired alert calculation；
- 不持久化 run、event、ledger、outbox 或 alert；
- 回傳 DB identity、batch、classifier version、排序 row ids、before／after tuple、
  counts 與 deterministic plan fingerprint。

Apply：

- 必須提供 Preview fingerprint、actor、idempotency key 與 expected batch version；
- 鎖後以同一 candidate builder fresh rebuild；
- fingerprint 不同時在任何 dispatch 前回傳 conflict；
- 全批一個 outer Unit of Work，任一列失敗全批 rollback；
- 只更新 changed classification-derived columns；
- 每個 changed row 建立一筆 append-only event；
- exact completed plan replay 回傳原 receipt，不重複 event 或 ledger。

已存在正式交易但 reconciliation 仍 pending 是 invariant violation，停止整批並送出異常 intent，不自動修復。

### 4.6 Query／Manifest

Modules：

- `FinanceImportBatchQuery`
- `FinanceImportRowQuery`
- `FinanceOccurrenceQuery`
- `FinanceReprocessRunQuery`
- `FinanceImportManifestMapper`
- `FinanceImportTypedResultMapper`

Query 永遠唯讀，不觸發 scan、reclassification、dispatch、alert refresh 或狀態轉移。API／CLI 只顯示 bounded summary；逐列結果必須使用明確 report export，且遮蔽敏感資料。

## 5. 正常匯入命令邊界

### 已確認

- 正常匯入與歷史重處理共用相同 normalizer、classifier、dispatch ports 與 transaction coordinator。
- 正常匯入必須支援 full-path dry-run，rollback 後不得留下 batch、row、occurrence、ledger、outbox 或 alert。
- Apply 是全批單一 transaction。
- canonical duplicate 不重複 dispatch。

### `FI-DEC-001` 已確認：自動 ingestion、人工確認正式帳務

File Watcher 偵測到 `downloads/bank/*.xlsx` 後，只允許自動：

- 驗證 stable file identity；
- 保存 batch、canonical bank facts 與 occurrences；
- 產生自動 classification；
- 建立 Finance Import Preview 與 anomaly intent。

不得自動建立 Client Finance／Staff Payables 等正式 ledger。人員必須先查看 Preview，
確認後才可 Apply typed dispatch。

Preview 至少顯示：

- 來源列數、canonical 新增數與 duplicate occurrence 數；
- 各帳務類型預計 dispatch 筆數與整數金額；
- 預計建立、已存在、待分類、business pending 與 blocked 數；
- 每筆預計關聯的案件、人員、義務及判定證據；
- 異常原因、嚴重度、是否阻擋 Apply 與 available actions；
- plan fingerprint、source content digest、classifier／fingerprint versions。

一般 `non_business_review` 可留在待處理區，不得被當成已入帳。資料完整性異常、
stale plan、fingerprint collision 或正式交易不一致則阻擋 Apply。

### `FI-DEC-002` 已確認：修改來源分流

人員不得直接修改 canonical bank fact，也不應把分類或主檔問題轉嫁成修改銀行 Excel。

依錯誤來源分流：

1. 銀行來源事實錯誤：
   - 不編輯已匯入 row；
   - 取得銀行正式更正版後重新 ingestion；
   - 舊 source／batch／occurrence 保留，追加 `SourceSuperseded` event；
   - 被 supersede 的 fact 不得 dispatch。
2. Parser／欄位投影錯誤：
   - 修正 versioned adapter 後對原 batch 重新 Preview；
   - 若會改 fingerprint，必須先有 fingerprint compatibility migration；
   - 不要求人員手改 Excel。
3. 客戶、月嫂、帳戶或義務主檔缺漏：
   - 由 owning Domain 介面修改主檔；
   - 修改成功後重新產生 Finance Import Preview；
   - Finance Import 介面不得直接改其他 Domain 根事實。
4. Classification／關聯目標有歧義：
   - 在 Finance Import Correction Workbench 選擇明確 classification 與既有 target；
   - 必填 actor、reason 與 evidence；
   - server 產生新的 manual decision candidate 與完整 batch Preview；
   - 最終 Apply 才原子寫入 append-only classification decision event 與正式 ledger。
5. 正式帳務已 Apply：
   - 禁止修改 Excel、canonical fact 或既有 ledger；
   - 只能由 owning Finance Domain 建立 reversal／adjustment／refund Preview→Apply。

介面可選 classification、合法 target、reason 與 evidence；不可編輯交易日期、金額、
方向、銀行帳號、cancellation code、raw payload、fingerprint、occurrence 或衍生狀態。

Modules：

- `FinanceImportCorrectionWorkbenchQuery`
- `ManualClassificationCandidateBuilder`
- `ManualClassificationEvidenceValidator`
- `SourceSupersessionCandidateBuilder`
- `CorrectionImpactPreviewBuilder`
- `CorrectionApplyPolicy`

### `FI-DEC-003` 已確認：異常存在時的 Apply 範圍

同一 Preview 中：

- 所有通過完整驗證的正式帳務 candidates 一次 Apply；
- `non_business_review` 與 business pending 保留待處理，不建立正式 ledger；
- integrity、collision、stale 或 formal-reference conflict 阻擋整批 Apply；
- 不提供任意勾選略過一筆「其實已完整驗證」的 candidate。

若人員認為某筆 candidate 不應入帳，必須先使用 Correction Workbench 提供原因與合法
target，重新產生 Preview；不得以無稽核的 checkbox 讓分類結果與 Apply 結果分離。

## 6. Anomalies Ports

### 6.1 `finance_import_manual_review`：帳務區待確認

普通 `non_business_review` 或分類／關聯目標暫時無法唯一判定的 canonical bank fact，
逐筆轉入警示中心「帳務」區，不留在「資料匯入異常」。已具有明確 business
classification、但正式核銷仍 pending 的列，改用 owning Finance Domain 對應的既有
finance alert code，不得一律改掛本代碼。Identity 綁定 canonical bank fact：

- `alert_code = finance_import_manual_review`
- `source_domain = finance_import`
- `source_type = canonical_bank_fact`
- `source_id = <finance_import_row_id>`
- 每個 canonical bank fact 最多一個 active review。

Finance alert 顯示：

- 不可變銀行日期、整數金額、方向及遮蔽帳號；
- 自動 classification、reason、合法候選對象與判定證據；
- affected obligations、預計核銷結果與 available actions；
- current fact version、alert version 與 idempotency identity。

人員在同一帳務工作區選擇 classification、合法 target、reason 及 evidence。Server
立即回傳 correction impact Preview；按下「確認修正並入帳」後執行
`CorrectAndPostFinanceImportRow`：

```text
lock canonical bank fact、alert version、target obligations
→ fresh rebuild correction candidate
→ 驗證銀行金額完整 allocation 且所選 obligations 精確歸零
→ append manual classification decision event
→ owning Finance Domain append ledger／allocation
→ append reconciliation receipt
→ append finance alert resolved event／outbox
→ commit
```

任一步驟失敗全部 rollback，警示保持 active。UI 不直接連 DB，也不得送出 raw amount、
derived balance 或 target status。若金額無法完整核銷，改提供 adjustment／refund／reversal
等 owning Domain action，不得硬寫帳務。

Exact retry 回原 receipt；相同 idempotency key 搭配不同 correction payload 固定 conflict。

### 6.2 `IMPORT-006`：資料匯入完整性異常

Finance Import 提供 `FinanceImportReviewDesiredState`，Anomalies 擁有 current alert projection。

Identity：

- `alert_code = IMPORT-006`
- `source_domain = IMPORT`
- `case_key = finance-import-batch:<batch_id>`
- 每 batch 最多一筆。

Allowed details：

- batch id、format id、來源檔顯示名稱、batch status／time；
- occurrence count、distinct canonical count；
- fingerprint collision、invalid canonical row、missing occurrence、
  non-pending inconsistency 與 partial batch counts；
- direction／reason counts；
- 最多 20 個 sample canonical row ids；
- 最近 reprocess run 的 bounded summary。

禁止 details：

- 姓名；
- 完整帳號；
- raw payload；
- 完整銀行列；
- 可用於猜測 identity 的非必要欄位。

Refresh：

- import completion／reprocess completion 寫入 outbox intent；
- projector post-commit create、update、resolve 或 reopen；
- projection failure 不回滾已提交的銀行根事實或正式 ledger；
- historical scan 是明確 Command，只讀根事實並更新 projection；
- 一般 Query 不 scan；
- rescan 不 reclassify、不 dispatch、不新增 finance occurrence。

Active predicate：

```text
active = integrity_inconsistent_count > 0
```

普通待分類筆數不啟動 `IMPORT-006`，只產生 6.1 的帳務待確認。Projection query 必須由
occurrence membership CTE、bounded aggregate、grouped counts、`LIMIT 20` sample 及
latest-run query 組成，不得把整批 canonical rows 載入記憶體。

Remaining 為零時自動 resolve；問題存在或再次出現時即使曾人工 resolve 也 reopen。Claimed alert 更新 details 時保留認領資訊。

## 7. Typed Commands／Results／Errors

Commands：

- `NormalizeFinanceWorkbook`
- `PreviewFinanceImport`
- `ApplyFinanceImport`
- `PreviewFinanceReprocess`
- `ApplyFinanceReprocess`
- `PreviewFinanceImportCorrection`
- `ApplyFinanceImportCorrection`
- `CorrectAndPostFinanceImportRow`
- `ScanFinanceImportReviewAlerts`
- `QueryFinanceImportBatch`
- `QueryFinanceImportRun`

Stable errors：

- `invalid_source_file`
- `unsupported_bank_format`
- `invalid_canonical_row`
- `strict_decode_failed`
- `batch_not_found`
- `batch_not_completed`
- `batch_too_large`
- `stale_preview`
- `idempotency_conflict`
- `classification_conflict`
- `manual_evidence_required`
- `source_superseded`
- `source_supersession_conflict`
- `reconciliation_invariant_violation`
- `dispatch_rejected`
- `downstream_unavailable`
- `transaction_failed`

只有 `downstream_unavailable`、deadlock 或明確 transient storage error 可依相同 idempotency identity bounded retry。Validation、stale、identity ambiguity 與 business rejection 不重試。

## 8. Transaction／Retry／Conflict

- Normalization 是 transaction 外的 pure phase。
- Preview 不持久化。
- Apply 取得 batch／row locks 後 fresh rebuild。
- 同一 Apply 的 batch、canonical row、occurrence、classification、owning Domain ledger、
  lifecycle intent、reprocess audit、idempotency receipt 與 outbox 共用 outer Unit of Work。
- 各 Domain port 不得自行 commit 或建立第二個 connection。
- Alert current projection 由 outbox post-commit 更新，不參與正式 ledger atomicity。
- Retry 必須沿用相同 canonical payload、idempotency key 與 expected version。
- 相同 key／相同 payload 回原 receipt；相同 key／不同 payload 固定 conflict。

## 9. Application Adapters

- File Watcher：只偵測 stable file、建立 command、呈現 typed outcome；不得連 DB、
  解析 manifest 或自行 upsert alert。
- Import CLI：只解析參數、呼叫 application contract、輸出 bounded summary。
- Reprocess CLI：預設 Preview；Apply 必須 actor、plan fingerprint、idempotency key。
- FastAPI：需要遠端管理入口時映射相同 contract，不另寫業務邏輯。
- Streamlit：只顯示 typed query／preview／apply result；本輪不提供 reprocess Apply UI。

現況 `scripts/file_watcher.py` 使用位置參數呼叫已要求 `--excel-path` 的 CLI，且自行處理 `IMPORT-002`；這是 live drift，不是新架構契約。

## 10. pytest 分層

### Module

- 各 adapter 對真實格式 fixture 的 canonical output。
- fingerprint version、duplicate identity 與 balance boundary。
- cancellation code projection。
- classification vocabulary 與 transition policy。
- plan fingerprint deterministic。
- typed error mapping。

### Subsystem

- 同檔／跨檔 duplicate 只新增 occurrence。
- staging 後 classifier／dispatch failure 全批 rollback。
- dry-run 零持久化。
- reprocess changed／unchanged／stale／exact replay。
- row lock 後失去 eligibility 時零 dispatch。
- `IMPORT-006` bounded privacy desired state。
- File Watcher／CLI 只呼叫 application contract。

### Domain

- Legacy、Sinopac、Taishin incoming／outgoing 完整流程。
- ambiguity 永不以姓名或金額猜測。
- Client Finance／Staff Payables 各自拒絕錯誤 allocation。
- classification 可完成但 reconciliation pending。
- formal transaction、classification、audit、receipt 與 outbox 原子一致。

### Global

- Finance Import → Client Finance → Orders deposit lifecycle → Anomalies。
- Finance Import → Staff Payables／Payroll → Anomalies。
- projector failure 後重試不重複 ledger。
- real-format Excel 加隔離 disposable MySQL；不得使用正式 `union_db`。

## 11. 現況吸收與退出

可吸收的現況：

- `finance_import_staging.py`
- `finance_transaction_classifier.py`
- `finance_import_states.py`
- `finance_import_dispatch.py`
- `finance_import_application.py`
- `finance_import_reprocessing.py`
- `finance_import_review_alerts.py`
- 兩支 thin CLI。

開始實作前必須修正的漂移：

- Application Service 函式過長且混合 orchestration、SQL、manifest 與 transaction。
- 正常匯入預設 Apply 且沒有 Preview fingerprint。
- File Watcher caller 參數已與 CLI contract 漂移。
- File Watcher 直接連 DB、寫 alert 且使用 replacement decoding。
- `project_finance_import_review_alert` 直接寫 Anomalies projection，Domain ownership 混合。
- 全交易 rollback 時 `failed` batch 不會持久存在，與 batch vocabulary 語意不完整。
- 部分既有 writer 仍直接修改 Orders status。

以上是 implementation gap，不得反向改寫本文件的目標邊界。
