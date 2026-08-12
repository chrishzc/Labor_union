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
- 上述 `CorrectAndPostFinanceImportRow` 只處理金額可精確核銷的一般分支。實際金額與義務
  不相等時，必須改走 Registry 指定的 Client Finance、Staff Payables 或 Government Subsidy
  專用 difference／overage command，並驗證「正式 allocation＋remaining／recovery／overpayment
  root＝完整銀行金額」；不得放寬一般 action 或由 Anomalies 自行拆帳。
- 上述「直接修正」只代表 UI 呼叫 typed backend command；UI 不得直接 SQL，且不得修改銀行
  日期、金額、方向、帳號、撤銷碼、raw payload、fingerprint 或 occurrence 等來源根事實。
- 操作成功後由新根事實驅動 projector 自動更新／解除 Alert；人工 resolve 不可取代正式操作。
- 原因或修復方式不唯一時只提供選項與證據，不預選、不自動 Apply。

### Typed Recovery Action Registry（2026-08-11，已人工確認）

`AnomalyDefinitionRegistry` 必須同時保存定義與有限 action descriptors。每個 descriptor 為
後端 typed result，至少包含：

- `action_key`、業務中文 `label`、`owning_domain`、`form_schema_key`；
- `source_bindings`：由 anomaly context 固定帶入、UI 不可改寫的 bank row、case、staff、
  obligation、recovery、batch/item identity 與 source version；
- `required_operator_inputs`：唯一選擇、reason、evidence、disposition 或 capability；
- `preview_operation`、`apply_operation`、required capability；
- `completion_predicate` 與 Apply 後應重新投影的 definition codes；
- action contract version。

每個 active finance definition 必須顯式二擇一：有完整 `available_actions`，或設
`no_automated_recovery=true`。兩者不可同時成立，也不可同時缺席；後者只代表 state-only，
不得由 UI、相容 API 或人工 resolve 補成未登記的金錢操作。

Registry 不保存衍生金額。Recovery context assembler 必須向 owning Domain Query 取得 current
remaining、候選 target 與 versions；UI 不得從 alert details JSON 或中文 message 推算 action。

#### 正式 action mapping

| Definition／predicate | Action key | 系統預填 | 人員可輸入 | 完成 predicate |
|---|---|---|---|---|
| `finance_import_manual_review` | `classify_and_post_bank_row` | bank row、batch、fact/alert version | 唯一 classification/target、reason、evidence | row 已由 owning Domain 正式 posting，manual-review predicate 消失 |
| `finance_import_manual_review`（選定客戶入款列） | `apply_client_receipt_overage` | incoming row | case、receivable obligation、收款階段、reason；歧義時唯一 target | receipt 全額存在、receivable 歸零、差額 refund payable 成立 |
| `client_refund_underpayment` | 無第二次 Apply（state-only） | 已建立的退款少匯 source | 無 | 原出款列已由 `finance_import_manual_review` 的客戶退款核銷 Preview／Apply 消費；後續只能以新的同帳戶出款列對原退款單 remaining 重走 Preview／Apply，全部結清才關閉 |
| `finance_import_manual_review`（選定客戶退款出款列） | `apply_client_refund_overage` | outgoing row | case、refund obligation、reason、evidence | refund obligation 歸零且同額差額 recovery root 成立 |
| `client_over_refund_recovery_open` | `collect_client_over_refund_recovery` | incoming row、client recovery | reason、evidence；歧義時唯一 recovery | recovery remaining 歸零或正確降低；原 overage anomaly 依 remaining 決定消失 |
| `finance_import_manual_review`（選定月嫂出款列） | `apply_staff_payout_difference` | outgoing row | `underpayment|overpayment`、同一月嫂 payable obligations、reason、evidence | payout 已記錄；少匯投影 remaining／partial，或多匯建立 staff recovery root |
| `staff_payout_underpayment`／`staff_payout_overpayment` | 無第二次 Apply（state-only） | 已建立的 payout difference source | 無 | 少匯在 remaining 清償後關閉；多匯在 recovery 結清／adjust 後關閉；不得重送已消費銀行列 |
| `staff_overpayment_recovery_open` | `collect_staff_overpayment_recovery` | incoming row、staff recovery | reason、evidence；歧義時唯一 recovery | recovery remaining 歸零或正確降低 |
| `GOVSUB-006` | `dispose_government_subsidy_overpayment` | incoming row、receipt、overpayment root、eligible targets | `offset|return`、合法 target／recipient snapshot、reason、evidence | overpayment 進入 offset 或 return payable 分支，不再 pending_review |
| `GOVSUB-007` | 無 Apply（state-only） | 已解析的 government outgoing row、唯一未結退款單、超額事實 | 無 | 實際多匯保持可見；不得由 alert 自動核銷、抵扣或新增付款義務 |
| `finance_import_manual_review`（選定出款列） | `reconcile_government_overpayment_return` | canonical outgoing row | government overpayment identity、reason、evidence；多筆候選時唯一退款單 | bank row 已對回退款單且 remaining 正確降低／歸零；退款單日期不是配對條件 |

同一 anomaly 若只有一個合法 action，UI 直接顯示該表單；有有限分支（例如政府 offset／return）
時，分支是同一 owning Domain Preview intent 的 enum，不是 UI 自由拼 endpoint。沒有完整 backend
action 時 `available_actions=[]` 並顯示「尚未支援此修復」，不得產生假按鈕。

#### UI dispatcher 邊界

UI 只依 `form_schema_key` 選擇已註冊的 typed renderer，renderer 必須對應單一 bounded Domain
API client。Dispatcher 不接收 raw endpoint、不用 definition code 寫業務 if/else，也不傳未驗證
dict。未知 contract version／schema key fail closed，顯示 `recovery_action_not_supported`。

所有表單流程固定：Query context → Preview → 顯示金額守恆／row changes／blockers → Apply →
顯示 receipt → 重新 Query anomaly。Apply disabled 直到 Preview 成功且 fingerprint、source version、
operator inputs 未改變。timeout 先查 receipt/job；不得換新 idempotency key盲目重送。

#### Registry 驗收

- 每個 active finance definition 必須明確為 `no_automated_recovery` 或至少一個 descriptor；
- action key、schema key、capability 與 contract version 唯一且可靜態驗證；
- source bindings 缺失、跨 Domain、stale 或多義時 Preview fail closed；
- completion predicate 仍成立時 anomaly 保持 open，不因 Apply receipt 或人工 resolve 假結案；
- 新增 definition 未登記 action 時 CI 失敗，但不影響只讀異常清單顯示。

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
- `RecoveryActionDescriptor`
- `RecoveryActionRegistryValidator`
- `TypedRecoveryFormSchema`

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
- `recovery_action_not_supported`
- `recovery_action_contract_version_mismatch`
- `recovery_source_binding_incomplete`
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
