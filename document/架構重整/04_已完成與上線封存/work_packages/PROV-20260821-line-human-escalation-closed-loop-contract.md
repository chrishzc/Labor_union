---
doc_type: work-package
declared_status: completed
identity: PROV-20260821-line-human-escalation-closed-loop-contract
date: 2026-08-21
owner: Customer Service / LINE Integration / Runtime Monitoring integration owner（待人工確認）
domain: Customer Service / LINE Integration / Runtime Monitoring
subsystem: Human Escalation、Automation Hold、Masked LINE Alert
scope: 收斂 M4「明確轉真人／綁定失敗／客訴／runtime critical」的 durable escalation、hold、通知與人工結案閉環
write_set:
  - document/架構重整/02_決策與退役執行記錄/PROV-20260821-line-human-escalation-closed-loop-contract.md
  - db/schema_parts/1002_customer_service_human_escalation.sql
  - db/migration_releases/labor_union_2026_08_21_customer_service_human_escalation_v1.json
  - db/migration_releases/labor_union_2026_08_21_customer_service_human_escalation_v1.descriptors.json
  - scripts/migrate_preserved_database_additive_schema.py
  - tests/integration/test_human_escalation_mysql_preserve_data.py
  - document/架構重整/03_追蹤清單與證據/evidence/PROV-20260821-customer-service-human-escalation/m4-db-verification-receipt.json
approval_required: M4-DB schema/release artifacts 與 disposable MySQL preserve 驗證已核准；禁止 current DB、production cutover、seed、backfill、destructive change
base_branch: main
base_head: f9240b9e3abbcf665b5c979e0973f675197d8494
dirty_baseline: integration-owner-must-capture-before-any-successor-writer
base_drift_rule: Customer Service ticket、LINE identity、runtime event、anomaly、M2 AI 或 outbox drift requires fresh read and re-freeze
db_change: additive schema/release artifacts plus disposable MySQL only; current DB and production cutover remain forbidden
external_provider: not approved; Phase 2 provider call remains zero until separate approval
---

# M4 LINE human escalation closed-loop contract 工作包

> 本文件凍結 Customer Service escalation owner 與 candidate inventory；M4-DB 的 additive schema/release artifacts 與 disposable MySQL preserve 驗證已獲核准。這不授權 current DB、production cutover、provider、LINE 發送或 deployment；M4-A application production write set 由獨立 implementation lane 管理。

## 0. 目標、邊界與固定結論

M4 要把「人明確要求真人／表示答錯」與可觀測的重大觸發，收斂成一條可重播、可稽核、可人工接手且能確實停止自動化的閉環：

```text
明確人工／答錯
連續兩次 binding failure
客訴 trigger／runtime critical
        ↓
Customer Service durable ticket + HIGH escalation
        ↓
automation hold（Phase 1 也停止 deterministic auto-reply）
        ↓
masked LINE alert intent（提交後由 outbox／delivery worker）
        ↓
claim → handling → resolve
        ↓
ticket resolved + hold release
```

固定結論：

1. Customer Service 擁有客服 ticket、conversation event、escalation 與 automation hold 的業務流程；LINE 只擁有 inbox、masked delivery intent、task、attempt 與 provider receipt；Runtime Monitoring 只提供 runtime event／health evidence。
2. 目前 `customer_service_tickets` 沒有 `priority`／`HIGH_PRIORITY` 欄位；本合同的 `HIGH` 是新 escalation 的 urgency，不得宣稱現有 ticket priority 已存在，也不得把 urgency 偷塞進現有 ticket category 或 status。
3. Phase 1 deterministic router 只可產生 M2 candidate 已定義的 typed `TicketReferral`／escalation intent；Phase 1 一旦 hold active，連 deterministic auto-reply 也停止。Phase 2 provider 尚未核准，hold active 或 approval 缺失時 provider 呼叫必須為零。
4. 所有 trigger、ticket、escalation、hold、audit、receipt 與 masked LINE intent 必須由一個 Customer Service outer Unit of Work 原子提交；LINE provider 永遠在提交後由 durable worker 執行。
5. 本合同不把 Scheduling 寫進 alert transaction：即使 runtime critical 的 component label 指向 Scheduling，也只保存去敏 runtime event reference，不鎖定、重算或修改 assignment、service date、leave、substitution、payroll 或任何 Scheduling root fact。

## 1. 權威與 live evidence

### 1.1 正式與候選依據

- `01_規格基線/00_Global_共同契約.md` §3、§4、§5、§7：跨 Domain 由 application 協調；外部副作用走 outbox；Alert 是 derived projection；人工 recovery 必須回 owning Domain Preview／Apply。
- `01_規格基線/15_正式規格索引與裁決總表.md` §2、§4：人工最新裁決優先；Anomalies 只擁有根事實異常 projection 與處理進度；Customer Service 擁有客服需求、對話、狀態與人工回覆。
- `01_規格基線/17_External_Integration_LINE_Access正式規格.md` §2、§3：外部事件先 canonical inbox，egress 由已提交 outbox／durable task；provider failure 不偽造下游成功。
- `01_規格基線/18_Global_Deployment與治理正式規格.md` §6：只對真正可觀測的 runtime facts 發出 alert；retry、去敏、人工 recovery 與 runtime owner 必須可追溯。
- `01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §3、§4：Customer Service ticket 是 owner；同一 LINE user＋category 最多一筆未完成 ticket；reply／delivery 同交易，provider exhausted 產生 runtime alert 但不回滾客服資料。
- `01_規格基線/23_LINE身分管理與解除正式規格.md` §3～§5：binding failure／provider failure 必須以 durable saga、outbox、retry 與人工入口處理，不可由 LINE 直接擁有客服狀態。
- `PROV-20260821-line-ai-router-architecture-decision.md`：已為 `approved-for-specification-freeze`；已定義 protected identity precedence、explicit human／wrong → `TicketReferral`、Phase 1 deterministic only、Phase 2 provider 未核准時不得呼叫。
- `PROV-20260820-line-runtime-alert-target-admin-contract.md`：已為 `approved-for-specification-freeze`；只負責 runtime alert target registration／reset／enable／disable，不擁有 Customer Service escalation 或 hold。

### 1.2 Live evidence 與 drift

- `domains/customer_service/ticket.py` 只有 `waiting → handling → resolved`（以及 resolved 重新 handling），沒有 urgency 或 automation hold。
- `subsystems/customer_service/application.py` 已有 ticket query、reply、Preview／Apply、idempotency、audit 與 LINE durable delivery 邊界，但沒有 escalation／hold application。
- `db/schema_parts/98_customer_service_tickets.sql` 的 `customer_service_tickets` 沒有 priority；現有 ticket event／status 不能單獨表達「停止自動化」或「LINE alert 已排入」。
- `domains/anomalies/registry.py` 的 `CurrentAlertProjection`／`AlertWorkflowStatus` 與 `claim_alert`／`resolve_alert_workflow` 管理 anomaly projection 的 `open／claimed／resolved`，不帶 ticket、HIGH urgency、hold scope 或 Customer Service conversation。
- `subsystems/line/runtime_alert_application.py` 目前將 runtime health event 投影為 LINE delivery task，且 registration writer 仍直接呼叫 group target；其 writer 退出與 target contract 由前一份 approved-for-specification-freeze contract 管理，implementation 仍待 successor。
- `api/routes/customer_service.py` 與 `api/schemas/customer_service.py` 的現有 endpoints／views 不含 escalation urgency、hold state、masked escalation intent 或 resolve hold gate。

上述都是 `live-drift`／缺口證據，不是本文件授權直接修改 code、schema 或既有資料。

## 2. Trigger catalog、root fact 與 ownership

### 2.1 四類 deterministic trigger

所有 trigger 必須來自已驗證的 canonical event；自由文字、模型自報分類、UI checkbox 或 operator 猜測不得直接建立 HIGH escalation。

| Trigger code | 觸發條件 | 最小可信來源 | hold scope |
|---|---|---|---|
| `explicit_human_request` | 使用者明確要求人工／客服／聯絡工會 | M2 `TicketReferral` 或 canonical LINE inbox event | 該 LINE conversation／客服 thread |
| `explicit_wrong_answer` | 使用者表示答錯／不對／無法解決 | M2 `TicketReferral` 或 canonical LINE inbox event | 該 LINE conversation／客服 thread |
| `binding_failure_threshold_2` | 同一 binding flow／subject scope 的**連續兩次** canonical binding failure，兩次之間沒有成功 binding；單次失敗不觸發 | LINE Identity binding failure events | 該 binding flow／subject scope |
| `complaint` | 已核准 deterministic complaint trigger catalog 命中客訴或重大情緒規則 | canonical LINE inbox event＋versioned trigger policy | 該 LINE conversation／客服 thread |
| `runtime_critical` | 已提交 `runtime_health_events.resulting_status=critical` 且 component／capability mapping 通過 allowlist | runtime health event／其 source reference | 受影響 capability scope；不得擴張成全部 LINE |

`binding_failure_threshold_2` 的「連續」是同一 flow／subject 的 event sequence property，不是任意時間內 count；source event identity、sequence/version 與 fingerprint 必須可重建。若 event 缺 identity、scope 不明、重送 payload conflict 或 mapping ambiguity，建立 typed operational finding，不能猜測成 HIGH ticket。

### 2.2 Root facts 與 derived values

Customer Service escalation 的 root facts：

- escalation ID、source event identity、source kind、source fingerprint、trigger code、trigger policy version；
- linked Customer Service ticket ID、ticket category、ticket version、LINE conversation scope 的 opaque reference；
- urgency=`high`、workflow status、workflow version、automation hold scope／state／version；
- actor、claim／handling／resolve timestamps、resolution evidence digest、idempotency／correlation identity；
- masked LINE alert intent identity、outbox／delivery task lineage 與 final delivery outcome reference。

Derived／query-only values：

- masked display label、ticket status label、目前可用 action、alert delivery summary、SLA／age label；
- 是否仍阻擋 automation、是否可 resolve、是否需要人工 recovery。

Customer Service 不擁有 LINE User ID、binding root、runtime health root 或 Scheduling root；只保存 opaque reference／去敏 snapshot，真正 root fact 仍由各 owning subsystem 提供並在 Apply fresh-read 驗證。

## 3. State machine 與 automation hold

### 3.1 Escalation／ticket state

```text
escalation: absent → open → claimed → handling → resolved
                         └──────────────→ resolved（僅在已核准的 direct handling transition）
hold:       absent → active → released
ticket:     waiting → handling → resolved
                         ↑          │
                         └──────────┘ 新訊息／新 escalation 重新開啟
```

- 建立 escalation 時，ticket 與 hold 必須同一交易建立；既有同 scope active escalation 的 exact source replay 只回原 receipt，新的同 scope事件 append 到既有 ticket／timeline，不另造競爭 hold。
- `claim` 只宣告 actor 取得工作，不等於 ticket 已回覆；`handling` 才可讓客服人員開始處理並將 ticket 轉 `handling`。
- `resolve` 必須鎖定 escalation、ticket、hold 與 source predicate，驗證 expected versions；只有 ticket 已由 typed Customer Service command 合法轉 `resolved`，且 resolution evidence 足以證明 trigger 已處理，才可在同一 UoW 將 hold `released`。
- runtime critical 不得因 anomaly auto-resolve 或 health poll 偶然變 healthy 就自動 release；必須由本合同的 resolve command 重新讀取 source predicate，或由明確核准的人工 recovery command 完成。
- binding failure hold 需有成功 binding receipt 或人工確認的替代聯絡結果；complaint／human／wrong hold 需有客服處理 evidence。無 evidence 固定 `hold_release_blocked`。
- resolved ticket 的新 canonical inbound event 可建立新 escalation；不得把舊 resolved receipt／hold 當成新事件成功。

### 3.2 Hold guard（不可旁路）

`CustomerServiceAutomationHoldGuard` 是所有自動回覆、deterministic Service Help 與未來 AI router 呼叫前的 typed query／port：

- hold=`active`：回 `automation_hold_active`，禁止 auto-reply、safe menu、knowledge answer、AI classification 與 provider call；只允許保存 inbox／escalation event 與顯示人工處理狀態。
- hold=`released` 或不存在：仍須通過原有 identity／group／Service Help／Knowledge policy；hold guard 不取代 owning Domain authorization。
- Phase 1 無 provider；即使 deterministic route 能判斷答案，也不得在 active hold 回覆。
- Phase 2 provider 未取得獨立 approval、provider metadata／PII policy／cost／timeout／kill switch 任一缺失，或 hold active，呼叫數固定為零。

Guard failure 不得被轉成空字串、假成功或「已通知」；需回 typed unavailable／blocked 並保留 escalation／hold。

## 4. Typed commands、views 與 errors

### 4.1 Commands／queries

```text
CreateHumanEscalation
  source_event_identity, source_fingerprint, trigger_code, trigger_policy_version,
  ticket_category, masked_context, hold_scope, actor=SystemPrincipal,
  idempotency_key, correlation_id

ClaimHumanEscalation
  escalation_id, expected_escalation_version, actor, idempotency_key, correlation_id

StartHumanEscalationHandling
  escalation_id, expected_escalation_version, expected_ticket_version,
  actor, idempotency_key, correlation_id

ResolveHumanEscalation
  escalation_id, expected_escalation_version, expected_ticket_version,
  resolution_code, resolution_evidence_digest, actor, idempotency_key, correlation_id

QueryHumanEscalation / QueryHumanEscalationTimeline / QueryAutomationHold
  bounded identifiers、masked filters、page／limit
```

`CreateHumanEscalation` 是跨 LINE／runtime source 的 typed intent gateway；它不得接受 raw LINE ID、完整原文、電話、姓名、provider payload、Scheduling ID 或任意 category／priority 字串。M2 router 不直接呼叫 repository；它只把 closed `TicketReferral` 交給此 gateway。

### 4.2 Closed views／receipts

```text
HumanEscalationView {
  escalation_id, ticket_ref, category, urgency="high",
  trigger_code, workflow_status, workflow_version,
  automation_hold: active|released, hold_scope_label,
  masked_context, alert_status, current_version,
  created_at, updated_at, available_actions[]
}

HumanEscalationReceipt {
  receipt_id, command_family, operation, escalation_id, ticket_ref,
  resulting_workflow_status, resulting_hold_state,
  current_version, replayed, correlation_id, committed_at
}
```

View／receipt 只回 server-defined masked labels、bounded trigger code、ticket reference、opaque version 與安全時間；禁止 raw LINE User ID／group ID、電話、姓名、完整訊息、internal note、provider ID／response、raw exception、SQL、token、signed URL secret、Scheduling facts。`alert_status` 只能是 `pending|queued|sent|failed|unknown` 的去敏摘要，不得把 task enqueue 當成 sent。

第一版 `masked_context` 採 closed allowlist，且 source、Customer Service domain、view 與 LINE alert intent
必須使用同一組欄位：

```text
summary_code, policy_version, category, redaction_version
```

`complaint.v1` 只接受 deterministic catalog 命中，輸出固定為
`summary_code=complaint_explicit`、`policy_version=complaint.v1`、`category=other`、
`redaction_version=m4-mask.v1`。不得保存原文、snippet、情緒分類、姓名、電話、LINE identity 或其他 PII；
`hold_scope_label` 是 view 的獨立去敏欄位，不屬於 `masked_context`。

### 4.3 Typed errors

- `human_escalation_source_invalid`（validation）
- `human_escalation_source_conflict`（conflict；source identity／payload 不一致）
- `human_escalation_not_found`（not_found）
- `human_escalation_version_conflict`（conflict；重新 Query／Preview）
- `human_escalation_transition_invalid`（domain_blocked）
- `human_escalation_duplicate_scope_active`（conflict；回既有 active escalation／receipt）
- `automation_hold_active`（domain_blocked；禁止 auto-reply／provider）
- `automation_hold_release_blocked`（domain_blocked；source predicate／ticket evidence 未滿足）
- `human_escalation_idempotency_mismatch`（idempotency_mismatch）
- `human_escalation_redaction_failed`（internal；不得提交 masked intent）
- `human_escalation_persistence_unavailable`（unavailable；可用同 key bounded retry）
- `human_escalation_outbox_unavailable`（unavailable；ticket／hold 交易不得部分成功）
- `human_escalation_provider_not_authorized`（domain_blocked；Phase 2 provider 未核准）

HTTP／internal error 一律遵守 Global 八欄 typed envelope；message 不回顯原文、identity、provider／DB 詳情或未遮罩值。

## 5. Transaction、idempotency、outbox 與 manual recovery

### 5.1 Create／trigger UoW

唯一 outer Customer Service UoW 順序固定為：

1. 驗證 canonical source event、trigger policy、masked context、category 與 hold scope；
2. 以 source event identity＋canonical payload fingerprint lookup receipt；same key／same payload 回原 receipt，different payload quarantine／conflict；
3. fresh-read／lock 同 scope active ticket、escalation、hold 與 source version；
4. create-or-append Customer Service ticket（沿用既有 category／status contract，不假造 priority），建立 HIGH escalation 與 active hold；
5. append typed escalation event、Customer Service management event、audit、idempotency receipt；
6. 建立只含 masked fields 的 LINE alert intent／outbox lineage；
7. 由唯一 owner commit。repository／adapter 不得 hidden commit；任何 ticket／escalation／hold／receipt／outbox 任一寫入失敗都 rollback。

### 5.2 Claim／handling／resolve UoW

- 每個 command 先查 replay，再以 expected escalation／ticket／hold version fresh lock；stale、unknown state、another actor claim 或 source conflict 不自動 retry。
- `claim`／`handling` 只保存 actor、version、event、audit、receipt；不呼叫 LINE provider，不改 runtime target，不改 anomaly root，不碰 Scheduling。
- `resolve` 重新查 source predicate、ticket status、escalation version 與 hold version；客服 typed reply／ticket resolve 與 hold release 必須在同一 UoW 完成，並建立 resolution evidence／receipt。
- 若 commit outcome unknown、connection lost 或 outbox receipt 缺失，API 不回成功；operator 以原 idempotency key Query escalation／ticket／hold／receipt，不產生新 key 猜測。

### 5.3 Masked LINE alert intent

LINE alert intent 只保存：`escalation_ref`、`ticket_ref`、`trigger_code`、`urgency=high`、masked category、bounded safe summary、hold state、correlation／source digest reference。recipient 由既有 LINE runtime target application 在提交後解析；本合同不指定、清除或重設 alert group。

delivery worker 只處理已提交 outbox／task。provider timeout／5xx／retry exhausted 不回滾 ticket、escalation 或 hold；failed／unknown 轉 typed runtime operational finding，alert view 不標示 `sent`。無 active alert target 時保留 escalation／hold，交人工 recovery，不自動改綁新群組。

### 5.4 Manual recovery

人工入口只允許 query masked escalation、claim、handling、typed resolve／hold release；不得 Data Browser PATCH、直接 SQL、重播 webhook 來偽造 source、手動清 hold 欄位或把 LINE provider success 當 ticket resolve。

若 source event identity／receipt／hold／delivery outcome 不一致，先停自動化並建立 operational finding；operator 必須以相同 command identity 查明實際 commit，再依 fresh source／ticket／hold state 修復。manual override 若日後需要，必須另立 command、capability、reason、evidence、audit 與 rollback contract，本文件不預授權。

## 6. Anomaly registry claim／resolve vs Customer Service persistence 裁決

### 6.1 比較

| 面向 | 重用 `anomaly registry` claim／resolve | 新增 Customer Service escalation persistence |
|---|---|---|
| 既有 owner | Anomalies，根事實 anomaly current projection | Customer Service，客服 ticket／conversation／人工處理 |
| 現有 state | `open／claimed／resolved`、predicate_active、workflow_version | 可明確保存 `HIGH`、ticket link、hold scope、claim／handling／resolve |
| 可否表達客服 | 無 ticket、message、category、客服 actor／reply 或 ticket version | 可與既有 ticket 同 UoW，保存 escalation event 與 handling evidence |
| 可否阻擋 automation | 無 hold invariant；resolve 不能安全代表 auto-reply 可恢復 | active hold 是獨立 root fact，release 受 ticket／source evidence gate |
| LINE alert lineage | anomaly query／workflow 可追蹤 projection | escalation 可擁有 masked intent、outbox、delivery outcome reference |
| 風險 | 將「看到／認領 anomaly」誤當「客服已處理／可恢復自動化」 | 需 schema／migration gate，且要避免與 anomaly workflow 重複命名 |

### 6.2 裁決建議

**不重用 anomaly registry 作為 primary human escalation persistence。推薦新增 Customer Service escalation persistence。**

- Anomaly registry 仍可作 `runtime_critical` 的 source／operational projection；其 `claim／resolve` 可供異常中心獨立追蹤，但任何 anomaly claim、auto-resolve 或 health recovery 都不得直接 release Customer Service hold。
- 新 escalation row 以 `source_anomaly_fingerprint`（若存在）或 runtime／LINE source event reference 建立關聯，不複製 anomaly 的 root fact、severity formula 或 recovery action。
- Customer Service escalation 的 `HIGH`、hold、ticket link、conversation evidence、LINE masked alert 與人工作業狀態由 Customer Service owner 單獨擁有；兩套 workflow 的 version／receipt／idempotency namespace 分開。
- 若人工希望只保留 anomaly table，必須另案提出「客服持久化、hold invariant、ticket link、HIGH urgency、masked alert、release predicate」的完整 schema／owner replacement contract；在該裁決前不可把既有 anomaly row 當 escalation。

## 7. Candidate schema inventory 與 DB gate

本合同只列 candidate inventory，沒有 SQL、seed、backfill、migration apply 或既有 DB 操作。

| 類別 | Candidate artifact／object | 資料效果、replay、rollback | 本次狀態 |
|---|---|---|---|
| `schema-only` | `customer_service_escalations`（new candidate）：ticket link、source identity／fingerprint、trigger policy、`urgency=high`、workflow／hold state、versions、actor／timestamps、resolution evidence digest、unique exact-replay／active-scope constraints | 只保存人工 escalation root；same source replay 回既有 receipt；rollback 需保留 source ticket／outbox lineage，不刪既有客服資料 | **candidate-only；spec planning PASS，未授權 DDL** |
| `schema-only` | `customer_service_escalation_events`（new candidate append-only）：create／claim／handling／resolve／hold-release event、expected/resulting version、actor、reason digest、receipt／correlation reference | 保存 immutable timeline；不得更新／刪除既有事件；rollback 需另案 recovery candidate | **candidate-only；spec planning PASS，未授權 DDL** |
| `system-seed` | 無 | 不預建 trigger row、priority row、recipient、HIGH ticket 或 default hold | **0 seed** |
| `business-row-backfill` | 無 | 不掃描／升格既有 Customer Service ticket、anomaly 或 runtime history；只有新 canonical trigger 產生新 escalation | **0 backfill** |
| `destructive` | 無 | 不刪 ticket、anomaly、LINE task、source event、recipient 或既有欄位 | **0 destructive** |

`HIGH` 應存在於新 escalation persistence，而非假裝現有 `customer_service_tickets.priority`；若人工選擇 alter parent ticket table 以加入 priority／hold，必須另列 altered parent descriptor、fresh／preserve-data migration 與 successor scope，本合同不包含。

### DB execution gate

| Gate | Status | Evidence／blocked reason |
|---|---|---|
| Scope gate | **PASS** | M4-DB exact schema/release artifacts 與 disposable MySQL preserve 驗證已人工核准；current DB／production cutover 明確禁止 |
| Change inventory | PASS | 2 個 schema-only tables、0 seed、0 business-row-backfill、0 destructive；parent schema 未改 |
| Static release gate | PASS | canonical release／assembly／validation manifest identity 已存在且 hash exact |
| Descriptor gate | PASS | canonical descriptor 覆蓋 columns、12 indexes、2 FK、12 checks、2 immutable triggers |
| Read-only plan gate | NOT_RUN | canonical default chain static inspection PASS；正式 source/candidate plan 需 disposable MySQL，Docker engine unavailable，本 lane 不碰 current DB |
| Engine verification gate | PASS | disposable MySQL preserve 驗證；僅 `lu_test_*` candidate/source，未觸 current DB |
| Developer acceptance gate | NOT_RUN | current DB／production replacement 未授權且禁止執行 |

結論：`DB_CHANGE_NOT_READY`。M4-DB candidate artifacts 與 disposable engine gate 已通過，但 developer acceptance 必須保持 `NOT_RUN`；不得將此證據解讀為 current DB 或 production ready。provisional identity 已由 integration writer late-bind 為 `labor-union-customer-service-human-escalation-2026-08-21-v1`，並保留 Rich Menu release dependency order。

## 8. M4-A implementation authority and future phased exact write sets

以下是 M4-A application successor projection。依 2026-08-21 人工裁決，Phase 1 的 production code／focused tests 已獲授權；本授權不包含 M4-DB current DB apply、React presentation、provider rollout 或其他外部副作用。M4-DB provisional artifact 已完成 late-bind，不得再以 provisional filename／ID 引用 canonical release。

### Phase 1：deterministic human escalation + hold + durable masked alert

**Customer Service／application owner（M4-A implementation-authorized）**

- `domains/customer_service/escalation.py`（new：escalation／hold state machine、trigger invariants、typed domain errors）
- `subsystems/customer_service/escalation_contracts.py`（new：commands、queries、views、receipts、ports）
- `subsystems/customer_service/escalation_application.py`（new：single outer UoW、fresh lock、idempotency、ticket link、hold release）
- `subsystems/customer_service/application.py`（narrow composition only：既有 ticket create／reply／resolve 與 escalation application 的 typed handoff）
- `infrastructure/mysql/customer_service_escalation_repository.py`（new：candidate persistence、event append、CAS／scope lock；不得 hidden commit）
- `infrastructure/mysql/line_unit_of_work.py`（wire new typed repository／outbox port；不得改 commit owner）
- `api/routes/customer_service.py`（新增 typed escalation query／claim／handling／resolve route；不新增 priority 假欄位）
- `api/schemas/customer_service.py`（新增 strict escalation request／view；extra forbid／redaction）

**LINE／runtime source adapter（M4-A implementation-authorized；只接已提交的 typed intent）**

- `subsystems/line/runtime_human_escalation_source.py`（new：binding threshold／complaint／runtime critical source normalization；不得寫 Scheduling）
- `subsystems/line/service_help_application.py`（M2 owner sole-writes Service Help 並接 `TicketReferral`；本 lane 僅經 typed escalation port，不競寫 `service_help` 或新增第二套 router）
- `subsystems/line/runtime_alert_application.py`（Runtime Monitoring／LINE target owner sole-writes；本 lane 僅接收已提交 masked escalation intent，不競寫 target registration／reset／enable／disable）

**Schema／release／tests**

- `db/schema_parts/1002_customer_service_human_escalation.sql`（canonical additive candidate tables；不得套用 current DB）
- `db/migration_releases/labor_union_2026_08_21_customer_service_human_escalation_v1.json` 與同名 `.descriptors.json`（canonical release／descriptor；保留 Rich Menu dependency order）
- `tests/customer_service/test_human_escalation_domain.py`
- `tests/customer_service/test_human_escalation_application.py`
- `tests/customer_service/test_human_escalation_api_contract.py`
- `tests/line/subsystems/test_human_escalation_source.py`
- `tests/integration/test_human_escalation_closed_loop.py`
- `tests/integration/test_human_escalation_mysql_preserve_data.py`

Phase 1 固定：0 AI provider、0 external provider call、0 Scheduling mutation、0 existing-ticket backfill、0 seed、0 destructive operation。只有 `TicketReferral`、binding event sequence、approved complaint trigger、runtime health event 通過 source validation 才能建立 escalation。

### Phase 2：guarded AI（仍需獨立 approval）

- M2 owner 的 `subsystems/line/ai_router_application.py`、`subsystems/line/ai_router_policy.py`、`infrastructure/ai/provider_gateway.py` 與其 tests／runbook 仍由 `PROV-20260821-line-ai-router-architecture-decision.md` 的 successor 管理；本合同不重複建立 provider writer。
- 本合同只允許在 `CustomerServiceAutomationHoldGuard` 回 `released`、M2 provider／PII／citation／cost／timeout／kill switch gates 全部 PASS 且另有人工 approval 時，接收 typed non-human outcome；任何 human／wrong、complaint、binding threshold 或 runtime critical 仍走 escalation。
- Phase 2 未取得核准時，exact acceptance 是 provider call count `0`，而非 mock success；hold active 時連 deterministic auto-reply 也禁止。

## 9. Acceptance、negative controls 與人工問題

### 9.1 Required acceptance

1. Trigger matrix 精確覆蓋 explicit human、explicit wrong、連續兩次 binding failure、complaint、runtime critical；單次 binding failure、unknown／ambiguous source、source conflict 不建立 HIGH escalation。
2. 每個新 trigger 都能在同一 outer UoW 建立／延續 Customer Service ticket、HIGH escalation、active hold、typed event、audit、receipt 與 masked LINE outbox；任一寫入失敗全 rollback。
3. 同 source／same idempotency payload exact replay 只回既有 receipt；different payload、stale version、duplicate active scope、unknown commit outcome 均 fail closed。
4. `CustomerServiceAutomationHoldGuard` 在 active hold 對 Phase 1 deterministic reply、safe menu、knowledge answer 與 Phase 2 provider 都回 `automation_hold_active`；不存在 hidden reply/provider call。
5. claim／handling／resolve 遵守 escalation／ticket／hold CAS；只有 fresh source predicate＋客服 resolution evidence 同時通過才 release hold；anomaly auto-resolve 或 runtime healthy poll 不可直接 release。
6. LINE intent 只含 allowlisted masked fields；delivery pending／failed／unknown 不得顯示 sent，provider failure 不回滾 ticket／escalation／hold。
7. existing ticket response 不出現虛構 `priority`；HIGH 只在 escalation view／persistence 表達；public／log／alert 不洩漏 LINE ID、姓名、電話、原文、provider payload 或 Scheduling fact。
8. Anomaly registry claim／resolve 與 Customer Service escalation claim／resolve 具獨立 namespace／receipt；任何 anomaly workflow transition 不可單獨改 hold。
9. 靜態與 runtime regression 證明 alert transaction 不寫 Scheduling，且 runtime critical 只保存 source reference／capability scope。

### 9.2 Negative controls

- 只有一筆 binding failure：0 ticket／0 escalation／0 hold。
- missing／conflicting source identity：0 mutation、typed error、quarantine／operational finding。
- active hold 下 deterministic route、M2 AI candidate、provider gateway：0 auto-reply、0 provider call。
- ticket resolved 但 runtime predicate 未清、binding 未成功或 evidence 缺失：hold 保持 active、`hold_release_blocked`。
- alert target disabled／missing 或 provider timeout：ticket／escalation／hold 保留，delivery 非 sent；不得自動 reset／rebind target。
- 同一 source 由兩個 worker 同時處理：單一 escalation／hold／receipt，另一方 exact replay／conflict，不得重複 LINE intent。

### 9.3 Human decisions required

1. 後續 implementation 是否依本 freeze 新增 Customer Service escalation persistence、Anomaly registry 僅作 source／operational projection？本問題不重新開放 ownership，僅確認 successor activation。
2. `binding_failure_threshold_2` 的 flow／subject scope 與「連續」事件保留期限／replay policy 由哪個 LINE Identity owner 核准？
3. complaint deterministic trigger catalog、masked summary allowlist、客服 category mapping 與人工 escalation window 由誰維護？
4. runtime critical 的 capability scope／owner／manual recovery predicate 如何定義；哪些 component 允許轉 Customer Service，而不擴張成全域 LINE hold？
5. `HIGH` escalation 的 SLA／排序／通知重試是否只存在新 escalation persistence；是否禁止任何 alter parent `customer_service_tickets` priority schema？
6. Customer Service operator 是否可由 `claim` 直接進 `handling`，或必須保留兩個明確 commands；resolve evidence 與 manual override 的核准者是誰？
7. M2 Phase 1 `TicketReferral` 與此 escalation port 的 shared hot spot owner、Phase 2 provider approval、PII／retention／cost／kill switch owner 為何？

## 10. Status、non-goals 與 handoff

本文件保持 `approved-for-specification-freeze`。不授權：

- 修改 Customer Service／LINE／Anomaly／Runtime production code、route、schema、DB、tests、README／index 或正式規格；
- 新增、填充或猜測現有 ticket priority／HIGH_PRIORITY；
- 把 anomaly claim／resolve 當作客服 resolve／hold release；
- 讓 LINE webhook、Streamlit、M2 router、repository 或 provider 直接寫 ticket／hold／DB；
- Phase 1／Phase 2 任何 auto-reply、AI provider、外部 LINE call 或 deployment；
- 在 alert transaction 內寫 Scheduling、排班、服務日、代班、薪資或付款。

Integration Owner 已將 M4-DB artifact late-bind 為 canonical release，並完成 static／descriptor／disposable preserve gates；仍須保留 current DB `NOT_RUN`。Customer Service application implementation、provider／external side effect 與 production cutover 仍依各自核准 write set 驗證，不由本 M4-DB receipt 擴張授權。

## 11. 2026-08-21 人工裁決：M4 escalation freeze

- Customer Service 擁有 escalation／hold／ticket link／HIGH／客服處理 evidence；Anomaly 只提供 source／operational projection，不得把 anomaly claim／resolve 當成客服 resolve 或 release hold。
- `HIGH` 只存在 `customer_service_escalations` candidate／typed view；不得新增或猜測既有 `customer_service_tickets.priority`。兩張 candidate tables 僅供 additive schema planning，0 seed、0 business-row-backfill、0 destructive，沒有 DDL 或 DB apply 授權。
- M2 owner sole-writes `service_help` 並接 `TicketReferral`；M4 escalation 只透過 typed port 建立／延續 escalation，不競寫 Service Help。Runtime Monitoring／LINE target owner sole-writes `runtime_alert_application`；escalation 只產生 committed masked intent，不競寫 target application。
- Scheduling、Orders、Assignment、Payroll 不在 escalation transaction；runtime critical 只保存 source reference／capability scope。`CustomerServiceAutomationHoldGuard` active 時 deterministic reply、AI candidate 與 provider call 數固定為 0。
- explicit human／wrong、連續兩次 binding failure、complaint、runtime critical 的 trigger catalog、threshold、SLA、retention 與 manual recovery 仍需後續 implementation acceptance；本 freeze 不宣稱 closed-loop production PASS。

### DB gate freeze

Scope、Change inventory、Static release、Descriptor：`PASS`；Read-only plan：`NOT_RUN`（僅 static inspection）；Engine verification：以既有 disposable receipt 為 `PASS`；Developer acceptance：`NOT_RUN`（current DB 禁止）。總結固定 `DB_CHANGE_NOT_READY`。

## 12. 2026-08-22 人工裁決：runtime-critical first-release mapping

M4 runtime-critical 第一版只接受 `component="LINE Worker"` 且
`capability_scope="line_delivery"` 的 committed critical event。component 與 capability 必須成對驗證；
Database、Media、Redis、Knowledge、unknown／global scope，即使重用 `line_delivery` 字串也固定 fail closed，
不得建立 Customer Service escalation 或 automation hold。

Runtime health 回復不會自動 resolve escalation 或 release hold。release 必須同時具備同一 source identity 的
committed healthy evidence，以及客服人員明確執行 typed resolve 並提交 resolution evidence；任一 identity、
component、capability、receipt 或版本不符，固定保留 active hold。這項裁決只授權既有 M4-A production path
與 focused tests 的 mapping／release predicate 收斂；0 schema、0 seed、0 backfill、0 destructive、0 current DB、
0 provider、0 deployment，亦不擴張為全域 LINE hold。

## 13. 2026-08-22 人工裁決：local current DB additive apply

最新人工裁決覆蓋本文件先前「current DB 禁止／Developer acceptance NOT_RUN」的局部限制，僅允許將
已通過 fresh／preserve qualification、hash-exact、schema-only 的 M4 release，以 30 秒 bounded local
in-place 路徑套用至 `lu_test_dataset_contract_signing_v4`。此裁決不授權 `union_db`、production、seed、
backfill、destructive、provider、deployment 或 source replacement。

2026-08-22 current-byte evidence：explicit qualification preview 為 `ready`；canonical runner 完成 6 個
allowlisted statements，runner DDL elapsed `5724ms`，baseline schema SHA-256
`3132a8a274fe30bb70ca60f54e35759890ec5117d2d55c03c0e0a6a0983c9c90`，post schema SHA-256
`cad34e9e7f213d8de9f5cf4e3e2da57ee9299ad7f786d7849f1836940935bcb3`。立即 readback 為 descriptor
`exact`，`customer_service_escalations=0`、`customer_service_escalation_events=0`。

| DB gate | Status | Evidence |
|---|---|---|
| Scope | PASS | 本節最新人工裁決；僅 local `lu_test_*` M4 schema-only apply |
| Change inventory | PASS | 2 tables／12 indexes／2 FK／12 checks／2 triggers；0 seed／backfill／destructive |
| Static release | PASS | canonical manifest／SQL／descriptor hash-exact qualification receipt |
| Descriptor | PASS | apply 後 canonical comparator `exact` |
| Read-only plan | PASS | explicit qualification preview `ready`、artifact `absent` |
| Engine verification | PASS | 既有 disposable fresh＋preserve qualification |
| Developer acceptance | PASS | fast in-place completed receipt與立即 readback |

DB 結論更新為 `DB_CHANGE_READY_LOCAL_APPLIED`；production／cutover 仍未授權。API create → claim →
handling → resolve E2E 本輪為 `NOT_RUN`：兩張 owned tables／events 具 immutable delete triggers，無法同時
滿足「commit 真實閉環」與「測後清理 owned rows」，不得停用 trigger 或留下假 cleanup evidence。

## 14. 2026-08-23 M4 current-byte backend／masking receipt

Current target registration／reset／enable／disable共用`RuntimeAlertTargetApplication`的advisory serialization、
fresh row lock、opaque CAS、receipt與audit boundary；API與Streamlit client使用closed typed view／receipt，
不暴露physical group/admin identity。Customer Service escalation保留create→claim→handling→resolve、active
hold release predicate與committed masked alert intent，LINE provider不在Customer Service transaction執行。

本輪再將`/api/v1/runtime/health-status`與`/health-events`掛上既有closed response models，避免dataclass
額外details穿透HTTP boundary；TestClient證明包含`group_id`／`access_token`的uncontracted details不出現在
response。涵蓋singleton target、typed target API/client、masking、escalation application/repository/API與
ticket adapter的focused suite為`66 passed`。0 schema、0 DB、0 provider、0 deployment。

此receipt只證明M4 backend／Streamlit typed slice；provider failure/recovery、React presentation與真實commit
human E2E仍`NOT_RUN`，M4 overall維持`partial / NOT_READY`。
