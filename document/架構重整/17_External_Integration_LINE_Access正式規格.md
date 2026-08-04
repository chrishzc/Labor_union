# External Integration、LINE 與 Access Control 正式規格

## 1. 文件狀態

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- BreezySign／LINE ownership：`consolidated-decision`
- Access Control：`consolidated-decision`
- live `line/line_bot.py` 的 integration bypass：`live-drift`
- 當前核准只啟用 Inventory v2 evidence；本文件 integration、Access、schema、
  pytest 與 legacy exit 條款不授權本輪修改 production 或外部平台。

## 2. Global Integration Boundary

### 2.1 共同不變量

1. 外部平台 Adapter 只驗證、正規化並保存外部事件。
2. 外部 payload、URL、actor、role、case mapping 與 provider status 都是不受信任輸入。
3. 外部事件不得直接指定 Orders status、actual dates、assignment、schedule、金額或付款狀態。
4. ingress 先保存不含敏感 raw payload 的 request-level security receipt；authenticity
   失敗只進 security quarantine／burst metric，不是可信事件。signature 與基本 envelope
   通過後才建立 canonical durable inbox event，再由獨立 consumer 呼叫 typed Domain Command。
5. 每個 egress 由已提交 outbox／durable task 執行；render／HTTP request 不直接發送。
6. provider event 與 downstream Domain command 使用不同的 idempotency identity。
7. 相同 event key＋相同 canonical payload 為 exact replay；相同 key＋不同 payload 為 conflict，
   必須 quarantine。
8. provider timeout／5xx 可 bounded retry；invalid signature、mapping ambiguity 與業務 blocker
   不可自動猜測。
9. Domain decision audit 與 Domain mutation 同交易；HTTP access／diagnostic audit 可 best-effort，
   但不得冒充 Domain audit。

### 2.2 Provider-neutral ports

- `ExternalSignatureVerifier`
- `ExternalEventNormalizer`
- `DurableInboxRepository`
- `ExternalEventConsumer`
- `DomainCommandGateway`
- `DurableDeliveryQueue`
- `ProviderDeliveryGateway`
- `ExternalEvidenceArchive`
- `IntegrationClock`

LINE、BreezySign 與 BeClass 可以共用 port contract，但不得共用模糊 payload table、
status enum 或 idempotency namespace。

### 2.3 Trusted system actor

自動 consumer 不冒用管理員。它使用 `SystemPrincipal`：

- 固定 service identity；
- versioned operation capabilities；
- deployment／release identity；
- correlation、source event 與 idempotency identity；
- 不可由 webhook payload、環境任意字串或 UI 指定。

SystemPrincipal 只能執行明確允許自動化的 typed Command；需要人類裁決的 blocker
必須建立 review／anomaly，不得提升 system capability。

### 2.4 Global typed errors

| Code | HTTP／處理 |
|---|---|
| `external_signature_invalid` | 401；不可 retry |
| `external_payload_invalid` | 400／422；不可 retry |
| `external_event_duplicate` | 回既有 receipt／ignored，不重複副作用 |
| `external_event_conflict` | 409＋quarantine |
| `external_mapping_not_found` | 404／人工處理 |
| `external_mapping_ambiguous` | 409／人工處理 |
| `external_provider_unavailable` | retryable 503 |
| `external_retry_exhausted` | failed＋alert |
| `integration_storage_unavailable` | 503；不回成功 |

## 3. Domain：Contract Integration／BreezySign

### 3.1 責任與 non-goals

Contract Integration 擁有：

- provider contract identity 與內部 contract aggregate 的受控 mapping；
- provider webhook durable inbox；
- signature evidence、canonical payload hash、provider occurred time；
- external contract event ledger 與 processing receipt；
- downstream contract evidence outbox。

不擁有：

- Orders lifecycle；
- actual service dates；
- waiting-deposit lock；
- assignment／schedule；
- LINE delivery 成功狀態。

### 3.2 根事實

- `provider`
- `provider_contract_id`
- `provider_event_id`；若 provider 無可靠 ID，使用 versioned canonical fingerprint
- `provider_event_type`
- `provider_contract_status`
- `provider_occurred_at`
- `signature_verification_result`
- `canonical_payload_hash`
- `received_at`
- `internal_contract_identity`
- `processing_attempts`
- `processing_outcome`

只保存驗證與稽核需要的最小 payload；敏感原文若必須保存，必須進受控 evidence archive，
不得進 log 或 UI。

### 3.3 State machine

Inbox：

```text
received → verified → normalized → applied
                   ├→ rejected
                   └→ retry_pending → applied | failed
```

External contract projection：

```text
pending_signature → signed | declined | cancelled | provider_failed
```

exact provider enum 必須由正式 provider contract 對照；未知值 fail closed，
不得 mapping 成 `signed`。

### 3.4 Subsystem：Contract Webhook Intake

Modules：

- `BreezySignSignatureVerifier`
- `BreezySignEventNormalizer`
- `ContractEventFingerprint`
- `ContractInboxRepository`
- `ContractMappingResolver`

交易：

1. 保存 request-level security receipt；signature 失敗則 quarantine 並停止；
2. 驗證 signature；
3. 正規化 canonical event；
4. 以 provider event ID／fingerprint durable insert；
5. 驗證 exact replay／payload conflict；
6. 綁定 internal contract identity；
7. append external contract event；
8. append downstream outbox 並單次 commit。

未知 contract、invalid signature 或 payload conflict 不產生 downstream Domain command。
invalid receipt 永遠不得轉成 canonical provider event；signature failure burst 由
security receipts 聚合告警，不需要保存不受信任的完整原文。

### 3.5 Subsystem：Contract Evidence Dispatch

Consumer 可以建立 `ContractCompletionEvidenceAvailable`，但不能自行 Apply Orders。

正式流程：

1. Orders Query 顯示已驗證 contract evidence；
2. 在 automation policy 尚未另經人工確認前，只有具 capability 的
   `AdminPrincipal` 可執行 `PreviewContractCompletion`；
3. `ApplyContractCompletion` 由 Orders outer Unit of Work 建立正式契約完成 root event；
4. 後續 Client Finance obligations 依既有跨 Domain 契約建立；
5. 不建立 assignment；等待訂金與第一個 assignment 仍走各自正式 Command。

`SystemPrincipal` 目前只可發出 `ContractCompletionEvidenceAvailable` outbox，
不得 Preview／Apply Orders；未來自動化是 public behavior 變更，須另行人工確認。

### 3.6 Alerts 與人工入口

- invalid signature burst；
- provider event key payload conflict；
- unknown／ambiguous internal contract；
- signed evidence 無 internal contract；
- retry exhausted；
- provider status regression。

人工入口只能重新 mapping、重試 normalization／dispatch 或標記 evidence 已釐清；
不得在 Integration UI 直接改 Orders、日期、assignment 或 schedule。

### 3.7 Live drift 與退出

`line/line_bot.py` 的 BreezySign webhook 目前：

- 未驗 provider signature、未 durable 去重；
- 以 `today + 10` 猜 actual start；
- 直接更新 Orders status／dates／service mode；
- 刪除並建立 legacy `staff_bookings`；
- 直接插入 LINE task 且可 fallback mock user；
- 例外 rollback 後仍回 success。

此路徑標為 `critical-integration-bypass`。正式 Work Package 必須移除 route，
或暫時固定回 `410 Gone`；不得包裝成相容轉接。

## 4. Domain：LINE Integration

### 4.1 責任與 SSOT

LINE Integration 擁有：

- LINE user／group platform identity 與 friend state；
- inbound webhook evidence；
- outbound delivery task 與 attempt ledger；
- identity binding review；
- Rich Menu definition／publication；
- LIFF platform verification evidence；
- media metadata與 content digest。

LINE 不擁有 Orders、Scheduling、Finance、Payroll 或 Staff Payables 狀態。

### 4.2 Subsystem：LINE Webhook Inbox

Canonical state：

```text
received → processing → completed
                     ├→ retry_pending → processing
                     ├→ failed
                     └→ ignored
```

同一 HTTP request 的多個 events 採：

1. ingestion transaction 原子保存全部可驗證 events；
2. 每個 event 有獨立 identity、狀態與 processing transaction；
3. 一個 event 失敗不回滾其他 event 的完成結果；
4. 缺可靠 `webhookEventId` 時使用 versioned canonical fingerprint；
5. 無法建立穩定 identity 時 fail closed，不直接處理副作用。

Modules：

- `LineSignatureVerifier`
- `LineWebhookNormalizer`
- `LineWebhookIdentity`
- `LineWebhookInboxRepository`
- `LineEventDispatcher`

### 4.3 Subsystem：LINE Delivery Task

State：

```text
pending → processing → sent
                   ├→ retry_pending → processing
                   └→ failed
pending → cancelled
failed → pending
stale processing → retry_pending
```

根事實：

- recipient identity；
- task type；
- immutable message／menu snapshot；
- scheduled time；
- source event identity；
- idempotency key；
- retry policy；
- attempt ledger；
- provider request／response identity；
- final receipt。

enqueue 必須接受 caller-owned transaction port，讓業務 outbox 與通知 task 原子建立。
duplicate idempotency key 必須回既有 task／receipt，不得只回 `None`。

retry 使用 bounded exponential backoff；非 retryable 4xx、invalid recipient、
content validation failure 直接 failed＋alert。

### 4.4 Subsystem：LINE Identity／Review

State：

```text
Friend: unknown → active ↔ blocked
Review: pending → approved | rejected | cancelled
Review assignment: assigned → reassigned | escalated
```

正式 approve／reject 必須：

- 使用 authenticated `AdminPrincipal`；
- 鎖定 pending request；
- 驗證 expected version 與目前 binding；
- 驗證新 LINE identity 未被其他主體占用；
- 保存 reviewer、reason、time 與 immutable decision event；
- 同交易更新 binding、enqueue stable-idempotency task 與 Domain audit。

legacy internal-key-only review／role mutation routes 不具人類授權，必須退出或 `410 Gone`。

Review 保存 `assigned_admin_id`、`assigned_at`、`due_at`、`reassignment_count` 與
expected version。超過 `due_at` 不自動批准／拒絕：

1. projector 產生 overdue alert；
2. `line_manager` 可 Preview／Apply reassignment；
3. 超過最大轉派次數或無可用 assignee 時進 `escalated`；
4. 原 assignee 的 stale decision 以 version conflict 拒絕；
5. timeout、轉派次數與 escalated owner 必須在 production policy 確認後設定。

### 4.5 Subsystem：Rich Menu／Media

Rich Menu publication：

```text
pending → processing → published
                     ├→ retry_pending
                     └→ failed
```

- Menu definition、image digest 與 publication snapshot 不可在 processing 後被覆寫。
- 發布採 create／upload／link／switch／cleanup 的 saga，每一步保存 receipt。
- retry 從已確認 provider receipt 繼續，不重複建立資產。
- media DB 只保存 metadata、owner、digest、size、content type 與 archive location，
  不保存任意外部 URL 當永久根事實。

## 5. Domain：Access Control

### 5.1 正式授權模型

採「角色配置 capability」模型：

- role 是管理與顯示用 bundle；
- operation capability 是 API 最終授權依據；
- `AdminPrincipal` 是唯一 human actor identity；
- `X-Internal-API-Key` 只證明受信任 service caller，不代表任何 human capability；
- body、query、UI session label 或任意 role 字串不得成為 actor。

初始角色 bundle：

| Role | 初始能力 |
|---|---|
| `line_viewer` | LINE read |
| `line_agent` | LINE read、review detail、task observation |
| `line_manager` | LINE review decision、task control、publication |
| `system_admin` | 全管理能力、帳號與安全設定 |

每個 Router 必須宣告 operation capability；階層比較只能作現有相容 adapter，
長期不得成為唯一 policy engine。

最小 capability registry：

- `line.identity.read`
- `line.identity.review`
- `line.task.read`
- `line.task.control`
- `line.menu.publish`
- `integration.event.read`
- `integration.event.retry`
- `admin.user.manage`
- `admin.session.revoke`
- `admin.audit.read`
- `data_browser.read`
- `data_browser.write`
- `system.configuration.manage`

新增 capability 是 public authorization contract 變更，必須更新 role bundle、Router
inventory、audit policy 與 authorization tests。

Command／Query 最小對照：

| Capability | Operations |
|---|---|
| `line.identity.read` | LINE identity／review Query |
| `line.identity.review` | Preview／Apply LINE review、reassignment |
| `line.task.read` | delivery task／attempt Query |
| `line.task.control` | retry／cancel delivery task |
| `line.menu.publish` | Preview／Apply Rich Menu publication |
| `integration.event.read` | contract／LINE inbox Query |
| `integration.event.retry` | retry eligible normalization／dispatch |
| `admin.user.manage` | create／enable／disable／assign role capability／rotate credential |
| `admin.session.revoke` | revoke admin session |
| `admin.audit.read` | security audit Query |
| `data_browser.read` | allowlisted read-only Data Browser Query |
| `data_browser.write` | allowlisted non-root-fact maintenance only |
| `system.configuration.manage` | versioned non-secret configuration mutation |

### 5.2 根事實與 state machine

根事實：

- admin user identity；
- password hash／credential version；
- enabled flag；
- role／capability grants；
- hashed session token；
- issued、expires、last-seen、revoked time；
- security decision audit。

State：

```text
Admin user: enabled ↔ disabled
Session: active → expired | revoked
Credential: valid → rotated
```

停權不刪除 user；role change、disable、credential rotation 都撤銷受影響 session。

### 5.3 Subsystem：Authentication／Session

Modules：

- `PasswordHasher`
- `AdminAuthenticator`
- `SessionTokenIssuer`
- `SessionRepository`
- `AdminPrincipalLoader`
- `AuthenticationPolicy`

正式環境：

- internal key 缺設定 fail closed；
- Bearer session 必須存在、有效、未撤銷且 user enabled；
- 原始 token 只回傳一次，DB 只保存 hash；
- `APP_ENV=production` 禁止 auth bypass；
- development bypass 必須同時是允許環境＋顯式設定，並產生醒目 audit／startup warning。

### 5.4 Subsystem：Authorization／Administration

Commands：

- `CreateAdminUser`
- `DisableAdminUser`
- `EnableAdminUser`
- `AssignAdminRoleCapabilities`
- `RevokeAdminSessions`
- `RotateAdminCredential`

每個 Command 使用 expected version、actor capability、reason 與 idempotency key。
禁止最後一位 `system_admin` 自我停權／降權，除非經獨立 break-glass procedure。

Ports：`AdminRepository`、`SessionRepository`、`CapabilityPolicy`、
`SecurityAuditRepository`、`SecurityOutbox` 與 `AccessControlUnitOfWork`。
role change／disable 依固定順序鎖定 user，驗證 expected version、capability 與
last-admin guard，寫入 grant／enabled event，撤銷受影響 session，append audit、
receipt／outbox，最後由 outer Unit of Work 單次 commit。相同 key replay 回既有
receipt；不同 payload、stale version 或並行 last-admin mutation 固定 conflict。

### 5.5 Subsystem：Security Audit

Domain decision audit 必須與 mutation 同交易保存：

- actor identity／role／effective capabilities；
- action；
- resource identity；
- before／after version或摘要；
- reason；
- correlation／idempotency identity；
- outcome 與 occurred time。

HTTP access log、latency 與 diagnostic audit 可獨立 best-effort，不能取代 Domain audit。
Generic Data Browser 不得修改 admin users、sessions、capabilities 或 security audit。

### 5.6 Typed errors

| Code | HTTP |
|---|---|
| `authentication_unavailable` | 503 |
| `invalid_internal_service_credential` | 401 |
| `missing_or_invalid_admin_session` | 401 |
| `admin_session_expired` | 401 |
| `admin_user_disabled` | 401／403 |
| `insufficient_capability` | 403 |
| `admin_version_conflict` | 409 |
| `last_system_admin_protected` | 409 |
| `security_audit_persistence_failed` | transaction rollback |

### 5.7 Alerts 與人工入口

- repeated login failure；
- disabled user session usage；
- production auth bypass attempt；
- unknown role／capability；
- last-admin mutation attempt；
- orphan／overlong session；
- Domain audit persistence failure。

管理入口提供 user enable／disable、role capability assignment、session revoke、
credential rotation 與 audit search；不得以 Data Browser generic PATCH 代替。

## 6. Domain：Case Import

### 6.1 責任與 SSOT

Case Import 擁有：

- BeClass／HCM 原始 row identity、source file digest 與 ingestion receipt；
- normalized candidate；
- validation result 與 privacy-safe review item；
- accepted source→internal identity mapping；
- case bootstrap command receipt。

不擁有 Client、Orders、Scheduling、Finance 或 Payroll 的正式根事實。正式 case 只能由
typed `ApplyCaseImport`／`ApplyBeClassReview` 委派各 owning Domain，在單一 outer
Unit of Work 建立。

### 6.2 State machine

```text
received → normalized → ready → applied
                     ├→ review_required → applied | rejected
                     └→ invalid
```

同一 source row identity＋相同 payload 是 replay；相同 identity＋不同 payload 是
source conflict。已存在 internal identity 時不得 insert-or-update 覆寫，必須進 review。

### 6.3 Subsystems／Modules

Subsystems：

- Source Intake／Normalization
- Validation／Identity Resolution
- Invalid-row Review
- Case Architecture Bootstrap

Modules：

- `SourceFileFingerprint`
- `BeClassRowIdentity`
- `HcmRowIdentity`
- `CaseImportNormalizer`
- `CaseImportValidator`
- `CaseIdentityResolver`
- `CaseBootstrapCandidateBuilder`

File Watcher 只建立 durable import job；CLI／Adapter 不直接寫正式 Client／Order。
invalid row 必須保存 privacy-safe root fact 並投影 canonical anomaly。

Typed operations：

- `IngestCaseImportSource` → `CaseImportIntakeReceipt`
- `PreviewCaseImport` → candidate、validation、mapping、fingerprint、expected version
- `ApplyCaseImport`／`ApplyBeClassReview` → bootstrap receipt 或 typed blocker
- `RejectCaseImportReview` → immutable rejection receipt

Ports：`CaseImportSourceArchive`、`CaseImportRepository`、`CaseIdentityQuery`、
`CaseBootstrapGateway`、`CaseImportOutbox`、`CaseImportClock` 與
`CaseImportUnitOfWork`。Apply 鎖定 source row、mapping 與 candidate version，
重建 fingerprint，透過 borrowed owning-Domain transaction ports 建立正式 roots，
再寫 mapping、receipt、outbox 後由唯一 outer Unit of Work commit。source identity、
payload digest 與 operation 組成 idempotency identity；stale／identity ambiguity
不重試，只有 storage unavailable／deadlock／timeout 可安全重試。

### 6.4 Typed errors／人工入口

- `case_import_source_conflict`
- `case_import_row_invalid`
- `case_import_identity_ambiguous`
- `case_import_candidate_stale`
- `case_import_already_applied`
- `case_bootstrap_failed`

人工入口只允許補正缺欄、選定唯一 identity、Preview bootstrap 與 Apply；
不得使用 Data Browser 或 importer fallback 改正式資料。

`RejectCaseImportReview` 只能由 pending／review-required 狀態執行，必須保存 reviewer、
reason、expected version 與 idempotency receipt；結果為 `rejected`，不得建立或修改
任何正式 Client／Order／Finance／Scheduling root fact。相同 key replay 回原 receipt，
stale review 固定 conflict。

## 7. Domain：Knowledge Retrieval

### 7.1 責任與 non-goals

Knowledge Retrieval 擁有：

- FAQ／policy content source、provenance、digest、版本與發布狀態；
- crawler／manual ingestion job 與結果；
- chunk／index artifact 的版本與 freshness；
- retrieval evidence 與 non-authoritative answer receipt。

不擁有訂單、排班、帳務、權限或個案決策。RAG 回答不得作為 Domain Command、
付款、資格、排班、退款或法律承諾的輸入。

### 7.2 State machines

```text
Knowledge item: draft → reviewed → published → retired
Ingestion job: pending → processing → completed | failed
Index build: requested → building → ready | stale | failed
```

只有具 content-publish capability 的管理員能發布。來源更新使舊 index `stale`；
stale／failed index 必須明確降級，不得用無來源模型答案假裝成功。

### 7.3 Subsystems／Modules

Subsystems：

- Knowledge Source Intake
- Human Review／Publication
- Index Build／Freshness
- Retrieval／Answer Composition

Modules：

- `KnowledgeSourceFingerprint`
- `KnowledgeItemVersion`
- `ContentSafetyValidator`
- `ChunkProjector`
- `IndexFreshnessPolicy`
- `CitationAssembler`
- `AnswerBoundaryPolicy`

### 7.4 Query、錯誤與人工入口

Query 回傳 answer、source identities、source versions、retrieved excerpts 的安全摘要、
index version 與 `authoritative=false`。

Typed errors：

- `knowledge_source_invalid`
- `knowledge_review_required`
- `knowledge_index_stale`
- `knowledge_index_unavailable`
- `knowledge_answer_unsupported`

人工入口提供 source review、publish／retire、reindex 與 failed job retry。
LINE 只負責 delivery，不擁有 FAQ／index 內容。

Commands／Queries：

- `IngestKnowledgeSource`、`SubmitKnowledgeReview`、`PublishKnowledgeItem`、
  `RetireKnowledgeItem`、`RequestKnowledgeIndexBuild`、`RetryKnowledgeJob`
- `QueryKnowledgeItem`、`QueryKnowledgeJob`、`QueryKnowledgeAnswer`

Ports：`KnowledgeSourceArchive`、`KnowledgeRepository`、`KnowledgeIndexGateway`、
`KnowledgeRetrievalGateway`、`KnowledgeOutbox`、`KnowledgeClock` 與
`KnowledgeUnitOfWork`。mutation 使用 item／job expected version、source digest 與
stable idempotency key；鎖定 item／job 後 append versioned event、receipt、outbox 並
單次 commit。stale publish、digest conflict、unsupported answer 不自動重試；只有
storage／provider transient failure bounded retry。legacy crawler／FAQ writer 必須改成
durable source job 或退出；LINE bot 不得直接更新 knowledge root 或無 citation 回答。

## 8. Human-decision-required

1. BreezySign 官方 signature header、algorithm、event ID 與 redelivery contract；
2. exact provider contract status enum；
3. 是否允許 BreezySign evidence 自動 Preview／Apply Orders；未決前固定 human-only；
4. LINE Rich Menu 正式發布是否要求雙人覆核；
5. LINE review timeout、最大轉派次數與 escalated owner；
6. session TTL、idle timeout、renewal ceiling；
7. security audit retention、遮罩與查閱能力；
8. break-glass credential 的保管人與演練頻率。

缺少以上值時，相應 production feature fail closed；不得使用 mock、固定 actor 或
development bypass 補上。

## 9. 分層驗收

### Module

- signature、canonical fingerprint、role→capability、session validity、state reducer。

### Subsystem

- duplicate／conflict／retry／stale processing；
- LINE task exact replay；
- review CAS；
- Contract mapping ambiguity；
- Domain audit failure rollback。

### Domain

- 隔離 MySQL unique event、row lock、attempt ledger、session revoke、append-only audit；
- invalid external event 不產生 business mutation。

### Global

- BreezySign signed event 不直接建立 assignment；
- LINE webhook redelivery 不重複 side effect；
- business commit＋LINE task 原子建立，provider failure 後可安全 retry；
- internal key 無 Bearer／capability 不得執行 human mutation；
- Integration／Access failure 不破壞 owning Domain transaction。
- invalid Case Import 不污染正式 Client／Order；
- Knowledge answer 無來源或 index stale 時 fail closed，且不能觸發 Domain mutation。

## 10. 來源追溯

- `document/文件整併工作區/03_API_LINE與自動化_無損合併稿.md`
- `document/文件整併工作區/05_潛在狀態機規則盤點.md`
- `document/文件整併工作區/06_欄位權威性與計算邏輯盤點.md`
- `api/dependencies/admin_auth.py`
- `services/admin_auth_service.py`
- `services/webhook_event_service.py`
- `services/line_task_service.py`
- `services/line_task_admin_service.py`
- `services/line_review_service.py`
- `line/worker.py`
- `line/line_bot.py`
- `db/schema.sql`
- `domains/case_import/`
- `subsystems/case_import/`
- `services/case_import_application.py`
- `services/case_import_hcm_adapter.py`
- `document/文件整併工作區/06_欄位權威性與計算邏輯盤點/10_知識與擷取紀錄/`

其中 `line/line_bot.py` 的越權路徑是 live drift 證據，不是正式規格來源。
所有 live source、schema 與 test evidence 必須在實作／驗收矩陣綁定 Git HEAD 或
content digest；本節列出的 path 不代表未來版本自動符合本規格。
