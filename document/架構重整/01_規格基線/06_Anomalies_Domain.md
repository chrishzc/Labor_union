# Anomalies Domain

## 1. Domain 定位

Anomalies 是根事實衍生的保護與人工作業 Domain，不是其他 Domain 的控制中心。

三層 SSOT：

1. 異常條件：各 source Domain 的根事實與正式事件。
2. 異常定義：`AnomalyDefinitionRegistry`，保存 code、source domain、fingerprint fields、severity、projection kind 與 display schema。
3. 工作流：
   - 財務敏感異常保存 immutable occurrence／event；
   - 流程與資料異常保存 current-state projection；
   - claim／resolve event 只代表人員處理進度。

Alert details JSON、UI 文案、review status 及 reconciliation pending 都不是異常條件 SSOT。

## 2. Subsystems

### Root-fact Detection

依 Domain event 增量偵測，並提供 bounded rescan。Detector 只讀根事實或 canonical projection，必須同時輸出 active 與 inactive desired state。可提早發現的缺漏應在下游流程前出現。

### Domain Blocker Projection

接收各 Domain blocker intent 並建立顯示投影，但 blocker authority 仍在 source Domain。Domain command 不得查 Alert status 決定成敗。

### Current-state Alert Projector

以 fingerprint upsert 唯一 current row。根條件消失自動 resolve；條件仍存在或再次出現時，即使曾人工 resolve 也必須 reopen。

### Finance Occurrence Recorder

每次新的銀行流水、重試批次或正式 Domain event 可形成 immutable occurrence。單純 rescan 不新增 occurrence；重試同一 source event 必須 idempotent。

銀行來源檔、canonical row、occurrence、classification 與 reprocess audit 的 owner 是
Finance Import Domain。Anomalies 不得直接解析銀行 raw payload、重分類或 dispatch。

Finance Import 的警示依根因分成兩條互斥路由：

1. 可安全保存、但暫時無法判斷業務歸屬的 canonical bank fact，建立
   `finance_import_manual_review` 財務警示。Identity 為
   `finance-import-row:<finance_import_row_id>`，同一 canonical row 同時最多一筆 active
   review，顯示於「異常警示中心 → 帳務」。
2. 解析缺列、fingerprint collision、occurrence 缺失、批次部分完成或狀態矛盾等
   匯入完整性問題，才以 `IMPORT-006` 投影至 canonical `anomaly_current_alerts`。Identity 為
   `finance-import-batch:<batch_id>`，每 batch 最多一筆，並阻擋該批正式 Apply。

一般 Query 不 scan；只有 import／reprocess outbox 或明確 bounded historical scan Command 可刷新。
Details 不得保存姓名、完整帳號或 raw payload。`IMPORT-006` 的 sample canonical row ids
上限為 20。普通待確認帳務不得同時再形成 `IMPORT-006`；若同一 row 另有完整性故障，
先顯示並處理阻擋型 `IMPORT-006`，完整性恢復後才投影可操作的財務待確認。

### Alert Workflow

```text
open → claimed → resolved
resolved --根條件仍存在或再次出現→ open
```

claim 使用 row lock／version；他人已認領回 conflict。resolve 必須有原因，但不得改正式帳務、derived amount、Domain blocker 或根事實。

### Query／Typed ViewModel

API 回傳 typed summary、detail 與 allowed actions。財務 occurrence 與 current reminder 可同頁顯示，但不能共用同一 status 語意。

### Human-assisted Recovery

異常中心必須讓人員完成「看懂 → 確認 → 操作」，但不直接修改任何 source Domain：

- 顯示觸發警報的根事實、事件時間線、目前差額、受影響訂單／assignment／義務及資料版本。
- 依 anomaly code 與 source Domain 回傳 typed `available_actions`，例如修正根事實、重新分類銀行流水、建立 adjustment Preview、建立 reversal Preview、補登服務日、重新 Preview 排班或重試 projector。
- 每個 action 只是一個 owning Domain command link／typed intent；Anomalies 不自行產生金額、日期、ownership 或 target status。
- 人員選擇 action 後先取得 owning Domain Preview，確認影響再 Apply。
- `finance_import_manual_review` 可提供 `CorrectAndPostFinanceImportRow`：
  人員選擇正確帳務類型與關聯義務後，後端在同一 transaction 鎖定 canonical bank fact、
  active alert 與所選義務，重新計算 candidate，驗證銀行金額完整 allocation 且每個所選
  義務精確歸零，再依序 append classification event、寫入 owning Finance ledger／allocation、
  reconciliation receipt 與 alert resolved event。任一步驟失敗全部 rollback。
- 上述「直接修正」只代表 UI 呼叫 typed backend command；UI 不得直接 SQL，且不得修改銀行
  日期、金額、方向、帳號、撤銷碼、raw payload、fingerprint 或 occurrence 等來源根事實。
- 操作成功後由新根事實驅動 projector 自動更新／解除 Alert；人工 resolve 不可取代正式操作。
- 原因或修復方式不唯一時只提供選項與證據，不預選、不自動 Apply。

## 3. Modules

- `AnomalyDefinitionRegistry`
- `DetectionPredicate`
- `AnomalyFingerprint`
- `SeverityPolicy`
- `DesiredAlertState`
- `BlockerIntentMapper`
- `BlockerCodeCanonicalizer`
- `SystemAlertReducer`
- `AutoResolvePolicy`
- `ReopenPolicy`
- `FinanceOccurrenceIdentity`
- `OccurrenceIdempotencyValidator`
- `ClaimPolicy`
- `ResolvePolicy`
- `WorkflowTransition`
- `AlertSummaryAssembler`
- `AllowedActionPolicy`
- `RecoveryContextAssembler`
- `DomainActionLinkBuilder`
- `RecoveryCompletionPredicate`

## 4. Ports 與交易

輸入：

- `DomainFactEventPort`
- `DomainBlockerIntentPort`
- `FinanceReconciliationOutcomePort`
- `FinanceImportReviewDesiredStatePort`
- `FinanceImportCorrectionCommandPort`
- `ClockPort`

基礎設施：

- `SystemAlertProjectionRepository`
- `FinanceAlertOccurrenceRepository`
- `AlertWorkflowEventRepository`
- `OutboxConsumerCheckpointRepository`

Projector transaction：

```text
lock outbox message + fingerprint
→ 驗證 event version／idempotency
→ append finance occurrence 或 upsert current alert
→ 更新 consumer checkpoint
→ commit
```

Projector 失敗可 retry，不回滾來源 Domain。claim／resolve 是獨立短交易。Rescan 只能 auto-resolve 自己 detector/code 範圍的 Alert。

## 5. 驗收

- fingerprint 穩定、duplicate event 不重複。
- active／inactive desired states 能清除舊提醒。
- resolve 後條件仍在會 reopen。
- 修正根事實後自動 resolve。
- Domain blocker 在 Alert resolved 時仍 fail closed。
- finance occurrence replay 不重複，單純 rescan 不新增 occurrence。
- projector 暫停後恢復不遺失事件。
- projector failure 不回滾來源 Domain。
- claim 並行只有一人成功，resolve 原因必填。
- 同一異常能顯示完整 recovery context，且每個 available action 都路由至正確 owning Domain。
- 不唯一的修復情境不會自動建立 adjustment、reversal、服務更正或狀態變更。
- 人員透過 owning Domain Preview／Apply 修正後，Alert 依新根事實自動解除。
- 一般待確認帳務只建立 `finance_import_manual_review`，不重複建立 `IMPORT-006`。
- `CorrectAndPostFinanceImportRow` partial failure 不留下單獨 classification、ledger、
  allocation、receipt 或 resolved alert。
- 銀行金額未完整 allocation 或任一所選義務未精確歸零時，零正式寫入並維持警示。

## 6. Typed Commands／Results／Errors

Commands：

- `QueryAnomalySummary`
- `QueryAnomalyDetail`
- `ClaimAnomaly`
- `ResolveAnomalyWorkflow`
- `ScanAnomalyDefinition`
- `RetryAnomalyProjector`
- `QueryRecoveryPreviewLink`

Results 分開回傳 source facts、workflow state、domain blocker、severity、timeline、
available actions、owning Domain、version 與 projection freshness；UI 不得解析 details JSON
推導 allowed action。

Stable errors：

- `anomaly_not_found`
- `anomaly_definition_not_found`
- `anomaly_claim_conflict`
- `anomaly_resolve_reason_required`
- `anomaly_version_conflict`
- `anomaly_source_fact_invalid`
- `anomaly_projection_stale`
- `anomaly_projection_data_integrity_violation`
- `recovery_action_not_available`
- `projector_unavailable`
- `transaction_failed`

## 7. Live writer 退出

- `services/anomaly_alert_detection.py` 與各 finance detector 只產生 typed desired state／fact，
  不直接寫 source Domain。
- `services/system_alert_service.py` 遷移為 current-state projector／workflow adapter；任意
  delete helper 不得用於正式根事實或 finance occurrence。
- `services/finance_alert_wiring.py` 的同步 caller wiring 改為 source Domain outbox。
- `services/finance_alert_workflow.py` 可吸收 claim／resolve concurrency，但不得修改正式
  ledger、差額或 blocker。
- `services/finance_import_review_alerts.py` 不得直接擁有 Finance Import 分類或 dispatch。
- final writer scan 必須證明 finance occurrence/event、system current projection、
  workflow events 與 consumer checkpoint 都只有 Anomalies adapters 可寫。
