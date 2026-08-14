# LINE、Access Control、Case Import 與 Knowledge 正式規格

## 1. 文件狀態

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- LINE ownership：`consolidated-decision`
- Access Control：`consolidated-decision`
- 2026-08-13 Case Import／LIFF entry split：`approved-by-IMPORT-ENTRY-02`
- 2026-08-14 Case Import 欄位級警示、外部追蹤與分域補件：`approved-by-WP88`
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
  fields、version 與 UoW 另行裁決，不能因入口位於 LINE 而把 root ownership 移給 LINE。WP77
  只裁決 restricted historical source 的 borrowed Staff writer；同 identity、姓名的來源以較新報名時間
  覆寫可更新 scalar，不擴張成 current profile owner；
- Client／Staff BeClass scripts 保留為 `restricted_historical_import`，只能處理明確 historical
  source，不能掛入一般 File Watcher、一般 Web upload registry，亦不得覆寫已由 LIFF／人工命令
  更新的 current facts。

2026-08-13 過渡例外：LIFF current registration／Staff profile writer 尚未完成 end-to-end 驗收前，
管理端「資料匯入中心」可提供 Client／Staff BeClass 的 authenticated temporary Web upload。
該入口只能呼叫各自 typed intake／HistoricalAdoption application，不得呼叫 browser SQL、File Watcher
或 script 的 direct writer；每張卡必須區分 `current`／`historical` 意圖、Preview／Apply、review
與 receipt。LIFF 對應 typed writer 已完成 API、UI、replay 與移除驗收後，temporary Web upload 必須
從 navigation、entrypoint queue 與 API 移除。HCM 與銀行流水沒有此過渡例外，固定由 Web upload。

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
source conflict。歷史 Staff operator 若取得同內容但較新的已確認來源版本，可明示 bounded
`source_revision`；它與 workbook digest 一起構成新的 source identity，且同 revision 固定 replay。
一般 current intake遇到已存在 internal identity時不得 insert-or-update覆寫，必須進
review。唯一例外是WP77核准的Staff HistoricalAdoption：identity與姓名一致且來源報名時間嚴格較新時，
覆寫可更新 scalar 並將最新來源時間保存為 `registered_at`；來源空值及 identity、LINE、status、系統
timestamps、unknown boolean 不覆寫。銀行與關聯集合同樣採empty-only保守合併。Staff歷史來源的
`IP位址`允許空值，空值以`NULL`保存且不建立review，不影響同列其他合法欄位落地。

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

HCM 不得以 fabricated default 補造欄位。案件編號是最低寫入資格：有可用案件編號時必須建立／保留
正式案件，其他欄位缺漏、格式錯誤或身份關聯歧義各自形成 durable field／link warning；只有案件編號
缺失或不可用時不建案、僅留來源警示。Client／Staff historical import 必須另走 HistoricalAdoption
Preview／Apply，不得重用 current LIFF command 假裝一般資料更新。

### 匯入異常的外部確認與重新提交

HCM、Client／Staff BeClass 與其他 Case Import 來源的 review 是公會人員聯絡來源當事人的待辦，
不是管理端直接修正資料的表單。review root、處理狀態與 disposition 必須保留去敏資訊；不得持久化
LINE 對話原文、完整聯絡資料或把回覆文字直接當成正式 Client／Order／Staff input。正確資料原則上由
新來源重新走 typed Preview／Apply；已建 HCM 案件的單一缺漏／無效欄位可由 HCM owning typed
field-completion command 補齊，不要求整案重送，也不得經警示中心直接改值。

WP77／WP88 將 HCM 與 Client BeClass 定義為可獨立存在的兩條 intake lane。HCM 案件編號不得重複；
IP＋姓名精確命中既有 Client、多候選或其他身份關聯歧義時，案件仍依案件編號建立，但不自動綁定 Client，
並建立獨立 link warning 供外部確認。HCM 歷史過渡模式只要符合最低寫入資格，即直接寫入來源的可寫欄位，
不推定目前 DB 值較有效；無法寫入的個別欄位仍各自警示。

Client BeClass 的 `query_no` 只是來源流水號，不得作為客戶識別或案件編號。LIFF 啟用前的過渡匯入只在
姓名＋手機完全一致且唯一命中 Client，且案件候選唯一時綁定；零筆或多筆候選都保留來源並警示，不允許
人工在警示中心挑選。LIFF 啟用後由登入身分直接綁定，不再使用這組過渡條件。

Staff BeClass 歷史匯入以有效身分證及姓名為最低資格。後來的歷史快照覆蓋可更新 scalar，銀行帳戶與勾選
關聯視為完整集合原子替換；姓名改變可寫入並留下已自動結束的追溯 warning。任一其他欄位缺漏或格式無效
仍建立欄位級 warning。Staff 退役不由匯入推定或修改。

有 HCM 而無唯一 Client BeClass 對方時投影 `BECLASS-001`；對方日後唯一綁定後由 root predicate 自動解除。
任何警示均以 `logical_code + field_path` 獨立追蹤；exact replay 不建立新 occurrence。顯式關聯的新提交仍
不合格時建立新 warning 並由 system 關閉被取代的舊 task；成功補齊後才 `auto_resolved`。所有來源、issue
codes、occurrence 與狀態事件保留。第一階段只記錄公會人工聯絡，不自動傳 LINE、不猜 recipient。

live `ApplyBeClassReview`／`RejectCaseImportReview` 的 corrected-fields／Correct／Reject 形狀不是核准目標；
必須依 entrypoint governance 退役或替換為 tracking-only transition 與 owning Domain typed command。

WP77最新裁決將HCM與Client BeClass定義為可獨立存在的兩條intake lane。HCM案件編號不得重複；
新案件若IP位址與姓名同時命中既有Client，視為疑似同一客戶重複申請，必須停止該列、建立review
並在警示中心通知公會人工確認。只有IP相同但姓名不同視為可能共用網路，不阻擋；Client BeClass尚未存在時仍可
建立Client／Order，`requires_cooking`保持`NULL`。Client BeClass亦可先獨立落地，不得因HCM缺失失敗。

兩方缺件屬可重建的current-state anomaly，不是匯入失敗：有HCM而無Client BeClass投影
`BECLASS-001`；有Client BeClass而無HCM投影`IMPORT-003 / beclass_hcm_mismatch`。對方日後匯入時，
reconciliation以案件編號及既有accepted mapping重新解析；唯一且一致才解除缺件
警示，多筆候選或互相衝突則保留兩方來源並進review，不得以姓名或電話相似度自動綁定。

只有唯一綁定後，reconciliation才可解析Client BeClass controlled cooking answer並透過typed Orders
command補入`requires_cooking`。missing／malformed／ambiguous／unsupported cooking答案屬BeClass
來源或配對後條款review，不得阻擋、回滾或刪除已建立的HCM Client／Order。`IMPORT-004`只保留給
HCM來源列本身的驗證失敗；不得把「缺少Client BeClass」誤投影成HCM validation failure。第一階段
不預建generic workbook manifest或尚未使用的Correct／Reject tables。

Typed operations：

- `IngestCaseImportSource` → `CaseImportIntakeReceipt`
- `PreviewCaseImport` → candidate、validation、mapping、fingerprint、expected version
- `ApplyCaseImport`／各 lane HistoricalAdoption Apply → 正式 root receipt、欄位級 warning 或 typed blocker
- `PreviewWarningTransition`／`ApplyWarningTransition` → 只更新外部追蹤狀態，不接受 corrected payload
- HCM owning field-completion／linking command → 補指定正式欄位或唯一關聯
- `AssociateImportResubmission` → 驗證 prior warning／source 與新 source／receipt 的明確關聯

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
- `import_warning_transition_not_allowed`
- `import_warning_resubmission_association_invalid`
- `import_warning_predicate_owner_unavailable`

警示中心人工入口只允許查詢去敏警示、推進外部追蹤狀態及導向已核准的 owning Domain typed command；
不得使用 Data Browser、importer fallback、generic corrected payload 或 candidate picker 改正式資料。
人工 `closed` 不等於 reject source 或 resolve root predicate。live `RejectCaseImportReview` 不得再作為正式入口；
退役前只能 fail closed，不得建立新的 rejection business meaning。

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
