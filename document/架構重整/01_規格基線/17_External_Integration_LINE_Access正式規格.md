# LINE、Access Control、Case Import 與 Knowledge 正式規格

## 1. 文件狀態

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- LINE ownership：`consolidated-decision`
- Access Control：`consolidated-decision`
- 2026-08-13 Case Import／LIFF entry split：`approved-by-IMPORT-ENTRY-02`
- 2026-08-03 原始核准只啟用 Inventory v2 evidence；後續 integration、Access、schema、
  pytest 與 legacy exit 的實作，必須各自依人工核准的 decision／Work Package 授權。

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

LINE 與 BeClass 可以共用 port contract，但不得共用模糊 payload table、
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

## 3. Domain：LINE Integration

### 3.1 責任與 SSOT

LINE Integration 擁有：

- LINE user／group platform identity 與 friend state；
- inbound webhook evidence；
- outbound delivery task 與 attempt ledger；
- identity binding review；
- Rich Menu definition／publication；
- LIFF platform verification evidence；
- media metadata與 content digest。

LINE 不擁有 Orders、Scheduling、Finance、Payroll 或 Staff Payables 狀態。

### 3.2 Subsystem：LINE Webhook Inbox

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

### 3.3 Subsystem：LINE Delivery Task

#### Matching Schedule Confirmation Delivery (2026-08-12)

The owning Matching/Scheduling subsystem creates immutable customer-parent and caregiver-segment
schedule snapshots only after a staff member explicitly sends a previewed, current confirmed
service-date version. LINE owns recipient binding, durable delivery tasks, interaction tokens,
and provider retries. If any required recipient lacks a LINE binding, the Send command fails
closed and creates neither snapshot nor delivery task.

LINE confirmation buttons append recipient-scoped events only after token, current snapshot and
bound LINE user checks pass. A rejection first enters `awaiting_rejection_reason`, sends a
durable text request, and becomes a rejected event only when a nonblank reply is received. The
webhook consumer must dispatch both postback and subsequent message through the same matching
schedule confirmation application; duplicate provider events reuse durable event identities.

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

### 3.4 Subsystem：LINE Identity／Review

State：

```text
Friend: unknown → active ↔ blocked
Review: pending → approved | rejected | cancelled
```

正式 approve／reject 必須：

- 使用 authenticated `AdminPrincipal`；
- 鎖定 pending request；
- 驗證 expected version 與目前 binding；
- 驗證新 LINE identity 未被其他主體占用；
- 保存 reviewer、reason、time 與 immutable decision event；
- 同交易更新 binding、enqueue stable-idempotency task 與 Domain audit。

legacy internal-key-only review／role mutation routes 不具人類授權，必須退出或 `410 Gone`。

待審案件沒有 `due_at`、逾期、自動核准、自動拒絕、轉派或 escalated state。它會以
建立時間由早到晚留在待辦佇列，直到具 `line.identity.review` 的真人管理員明確核准、
拒絕或取消；系統只可顯示待辦數量，不得以時間推導任何決定。

### 3.5 Subsystem：Rich Menu／Media

Rich Menu publication：

```text
pending → processing → published
                     ├→ retry_pending
                     └→ failed
```

- Menu definition、image digest 與 publication snapshot 不可在 processing 後被覆寫。
- 發布採 create／upload／link／switch／cleanup 的 saga，每一步保存 receipt。
- retry 從已確認 provider receipt 繼續，不重複建立資產。
- 身分綁定成功必須在同一交易 enqueue 個人 Rich Menu binding intent；worker 解析該身分角色
  最新已發布的 provider menu 後執行 link，identity binding 不因外部 API 暫時失敗而回滾。
- 新 Rich Menu publication 成功時，必須在記錄 published 的同一交易，依 menu audience role
  對全部 bound LINE identities fan-out 個人 binding intents。每筆 intent 以 publication ID 與
  LINE user ID 組成冪等 identity，並固定本次 provider menu ID；既有身分不需要解除或重複綁定。
- media DB 只保存 metadata、owner、digest、size、content type 與 archive location，
  不保存任意外部 URL 當永久根事實。
- 正式套用採單人流程：管理員先看到目前 menu snapshot 的預覽，再按「確認目前預覽」取得
  server-side preview receipt，最後勾選二次確認才可 Apply。Apply 必須鎖定同一管理員、
  同一 menu、同一 config revision 與 fingerprint；任一內容變更使舊預覽失效。沒有雙人覆核。

## 4. Domain：Access Control

### 4.1 正式內部使用者存取模型

2026-08-12 最新人工裁決：所有已登入且 enabled 的內部使用者具有相同業務功能權限。本系統不以
role、capability、職稱或部門限制內部使用者可操作的業務功能，也不採 fixed role bundle、dynamic
grant／revoke、階層比較或雙人權限覆核。

- `AdminPrincipal` 是 human actor identity，用於 authentication、操作歸屬與 audit，不代表差異化權限。
- 業務 API 只判斷 session 是否有效且 user 是否 enabled；通過後可使用相同業務功能集合。
- `X-Legacy-Shared-Key` 只證明受信任 service caller，不能冒充 human actor。
- body、query、UI session label 或任意 role／capability 字串不得成為 actor 或改變可用功能。
- UI 不顯示依人員而異的業務選單，也不建立「有權／無權角色」驗收案例。
- 外部 provider、production environment、secret、資料庫 target、SystemPrincipal 自動命令範圍及
  Preview／Confirm／Apply 等安全門禁不屬於人員差異化權限，仍須遵守各自契約。

### 4.2 根事實與 state machine

根事實：

- admin user identity；
- password hash／credential version；
- enabled flag；
- hashed session token；
- issued、expires、last-seen、revoked time；
- security decision audit。

State：

```text
Admin user: enabled ↔ disabled
Session: active → expired | revoked
Credential: valid → rotated
```

停權不刪除 user；disable、credential rotation 都撤銷受影響 session。

### 4.3 Subsystem：Authentication／Session

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
- session 每次有效請求會滑動延長為 30 分鐘閒置期限，但首次登入起最多 8 小時；到達
  absolute deadline 後即使持續操作也必須重新輸入密碼。舊 session 缺少 absolute deadline
  時 fail closed；
- `APP_ENV=production` 禁止 auth bypass；
- development bypass 必須同時是允許環境＋顯式設定，並產生醒目 audit／startup warning。

### 4.4 Subsystem：Account／Session Administration

Commands：

- `CreateAdminUser`
- `DisableAdminUser`
- `EnableAdminUser`
- `RevokeAdminSessions`
- `RotateAdminCredential`

每個 Command 使用 expected version、authenticated actor、reason 與 idempotency key。本系統不採用
break-glass credential、緊急繞過 API 或自動復原流程。

Ports：`AdminRepository`、`SessionRepository`、`SecurityAuditRepository`、`SecurityOutbox` 與
`AccessControlUnitOfWork`。disable 依固定順序鎖定 user，驗證 expected version 與 authenticated actor，
寫入 enabled event，撤銷受影響 session，append audit、
receipt／outbox，最後由 outer Unit of Work 單次 commit。相同 key replay 回既有
receipt；不同 payload或 stale version 固定 conflict。

### 4.5 Subsystem：Security Audit

Domain decision audit 必須與 mutation 同交易保存：

- actor identity；
- action；
- resource identity；
- before／after version或摘要；
- reason；
- correlation／idempotency identity；
- outcome 與 occurred time。

HTTP access log、latency 與 diagnostic audit 可獨立 best-effort，不能取代 Domain audit。
Generic Data Browser 不得修改 admin users、sessions、capabilities 或 security audit。

2026-08-09 已採用 Security Audit policy：所有已登入且 enabled 的內部使用者可查最近兩年的 audit
摘要；清單固定遮罩 IP，明細固定遮罩 token、password、
Authorization、LINE user ID、電話與身分證等敏感值。所有已登入管理員可直接查看已遮罩明細。
此為唯讀查詢，不要求填寫查閱原因，也不另寫入 Domain decision event；`reason` 僅是會改變
資料、綁定、授權或核准結果的 Command audit 欄位。
超過兩年的線上紀錄由每日 bounded worker 移至
不對管理 UI 開放的 archive；archive 不自動刪除。

### 4.6 Typed errors

| Code | HTTP |
|---|---|
| `authentication_unavailable` | 503 |
| `invalid_internal_service_credential` | 401 |
| `missing_or_invalid_admin_session` | 401 |
| `admin_session_expired` | 401 |
| `admin_user_disabled` | 401／403 |
| `admin_version_conflict` | 409 |
| `security_audit_persistence_failed` | transaction rollback |

### 4.7 Alerts 與人工入口

- repeated login failure；
- disabled user session usage；
- production auth bypass attempt；
- orphan／overlong session；
- Domain audit persistence failure。

管理入口提供 user enable／disable、session revoke、credential rotation 與 audit search；不得以
Data Browser generic PATCH 代替。

## 5. Domain：Case Import

### 5.1 責任與 SSOT

Case Import 擁有：

- BeClass／HCM 原始 row identity、source file digest 與 ingestion receipt；
- normalized candidate；
- validation result 與 privacy-safe review item；
- accepted source→internal identity mapping；
- case bootstrap command receipt。

入口裁決 `IMPORT-ENTRY-02`：

- HCM 日常來源以 authenticated Web upload 進入 Case Import Source Intake；其 adapter 應沿用
  Finance Web upload 的 bounded upload、ephemeral cleanup、typed receipt 與 replay 邊界；
- Client BeClass 現行資料由 LIFF 驗證身分後呼叫 typed registration／profile API；LINE 只擁有
  platform identity 與驗證 evidence，正式資料仍由各 owning Domain command 寫入；
- Staff profile 的核准目標同樣為 LIFF → typed API，不得由 browser 直接 SQL；live 目前只有
  Staff identity binding 與 orders／schedule Query，尚無 profile writer。Staff profile owner、root
  fields、version 與 UoW 另行裁決，不能因入口位於 LINE 而把 root ownership 移給 LINE；
- Client／Staff BeClass scripts 保留為 `restricted_historical_import`，只能處理明確 historical
  source，不能掛入一般 File Watcher、一般 Web upload registry，亦不得覆寫已由 LIFF／人工命令
  更新的 current facts。

不擁有 Client、Orders、Scheduling、Finance 或 Payroll 的正式根事實。正式 case 只能由
typed `ApplyCaseImport`／`ApplyBeClassReview` 委派各 owning Domain，在單一 outer
Unit of Work 建立。

### 5.2 State machine

```text
received → normalized → ready → applied
                     ├→ review_required → applied | rejected
                     └→ invalid
```

同一 source row identity＋相同 payload 是 replay；相同 identity＋不同 payload 是
source conflict。已存在 internal identity 時不得 insert-or-update 覆寫，必須進 review。

### 5.3 Subsystems／Modules

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

HCM validation 失敗時不得用 fabricated default 建立正式 Client／Order；必須形成 durable
`review_required` outcome。Client／Staff historical import 必須另走 HistoricalAdoption Preview／Apply
及 no-impact gate，不得重用 current LIFF command 假裝一般資料更新。

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

### 5.4 Typed errors／人工入口

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

## 6. Domain：Knowledge Retrieval

### 6.1 責任與 non-goals

Knowledge Retrieval 擁有：

- FAQ／policy content source、provenance、digest、版本與發布狀態；
- crawler／manual ingestion job 與結果；
- chunk／index artifact 的版本與 freshness；
- retrieval evidence 與 non-authoritative answer receipt。

不擁有訂單、排班、帳務、權限或個案決策。RAG 回答不得作為 Domain Command、
付款、資格、排班、退款或法律承諾的輸入。

### 6.2 State machines

```text
Knowledge item: draft → reviewed → published → retired
Ingestion job: pending → processing → completed | failed
Index build: requested → building → ready | stale | failed
```

所有已登入且 enabled 的內部使用者都能執行發布。來源更新使舊 index `stale`；
stale／failed index 必須明確降級，不得用無來源模型答案假裝成功。

2026-08-09 已採用並實作：content author 不得覆核自己建立的 draft，content author 也不得
發布自己的內容；只有 `published` item 能被查詢。答案必回 source URI、content digest 與
published version，且固定 `authoritative=false`。舊 Chroma FAQ 直接回答維持退役；無來源、
stale 或查詢失敗時 LINE 轉人工，不得編造答案。

### 6.3 Subsystems／Modules

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

### 6.4 Query、錯誤與人工入口

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

## 7. Human-decision-required

無。

本節原先列出的所有人工作業政策均已決定；任何後續 policy 變更仍須先更新決策記錄，
不得以 mock、固定 actor 或 development bypass 補上。

## 8. 分層驗收

### Module

- signature、canonical fingerprint、session validity／enabled user、state reducer。

### Subsystem

- duplicate／conflict／retry／stale processing；
- LINE task exact replay；
- review CAS；
- Domain audit failure rollback。

### Domain

- 隔離 MySQL unique event、row lock、attempt ledger、session revoke、append-only audit；
- invalid external event 不產生 business mutation。

### Global

- LINE webhook redelivery 不重複 side effect；
- business commit＋LINE task 原子建立，provider failure 後可安全 retry；
- internal key 無有效 internal-user session 不得執行 human mutation；
- Integration／Access failure 不破壞 owning Domain transaction。
- invalid Case Import 不污染正式 Client／Order；
- Knowledge answer 無來源或 index stale 時 fail closed，且不能觸發 Domain mutation。

## 9. 來源追溯

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
