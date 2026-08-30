# LINE、Access Control、Case Import 與 Knowledge 正式規格

## 1. 文件狀態

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- LINE ownership：`consolidated-decision`
- Access Control：`consolidated-decision`
- 2026-08-13 Case Import／LIFF entry split：`approved-by-IMPORT-ENTRY-02`
- 2026-08-14 Case Import 欄位級警示、外部追蹤與分域補件：`approved-by-WP92`
- 2026-08-03 原始核准只啟用 Inventory v2 evidence；後續 integration、Access、schema、
  pytest 與 legacy exit 的實作，必須各自依人工核准的 decision／Work Package 授權。
- 2026-08-21 LINE four-module specification freeze：M1 Alternative A、M2 deterministic Phase 1、M3
  Scheduling Matching Coordination Phase A–D、M4 runtime target／human escalation ownership 已核准；
  後續人工已核准 M1-A、M2-A、M3-A～D、M4-A 的 exact production implementation slice；這不擴張為
  provider、deployment、production DB、未另行核准 schema 或其他外部副作用授權。

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

#### LINE Configuration typed／redacted query（2026-08-20）

LINE Configuration 提供 authenticated、query-only 的
`GET /api/v1/line/configurations/{kind}/safe`，`kind` 僅接受已凍結的六個 closed kinds。
成功資料只允許 `kind`、non-negative `revision` 與 `state=empty|configured`；canonical definition `{}`
固定為 `empty`，其餘 canonical object 為 `configured`。既有 full-definition GET 保留為 compatibility
projection，不由本 query 取代或退役。

safe query 不得輸出 definition、URL／URI、action data、image、secret、token、credential、provider identity、
payload、actor、correlation、reason、idempotency 或 LINE recipient identity。snapshot kind mismatch、malformed
revision／canonical object 與 repository unavailable 必須 typed fail closed；success、empty、invalid 與 unavailable
路徑均不得 commit、append audit／receipt／outbox、wakeup 或呼叫 provider。

#### Delivery public observation query（2026-08-20）

LINE Delivery 提供 authenticated、typed、server-masked summary/list/detail queries；公開欄位限 bounded status、
safe task/source label、attempt count 與時間欄位。recipient identity／type、payload、message preview、provider ID、
correlation、raw error、source identity 與 worker runtime detail 均不得穿透。list filter 僅可使用 server-defined
allowlist，`user_id`、recipient identity 與 arbitrary source identity filter 必須拒絕；page size 為 bounded page
限制，total/page metadata 必須支援超過單頁上限的資料集，不得先載入固定上限後在記憶體假分頁。

Query 必須 0 commit、0 enqueue、0 worker wakeup、0 provider call；malformed repository item、unknown enum、extra
sensitive field 與內部例外均須在 route/application boundary typed fail closed。cancel、run-now、retry、React caller
adoption 與 provider rollout 不因本 query 契約而被授權。

#### Identity review numbered observation query（2026-08-25）

管理端 LINE 身分審核清單使用 additive
`GET /api/v1/line/identity/reviews/numbered`；只接受 closed `review_status`／`review_type`、positive `page`
與 bounded `page_size`，回傳 strict `items/page/page_size/total`。既有
`GET /api/v1/line/identity/reviews` cursor contract 保留為 compatibility projection，不得改義或退役。

numbered query 必須以 repository `COUNT` 與 `LIMIT/OFFSET` 取得 server metadata，不得先載入固定上限再於
React 記憶體切片。管理端篩選變更固定回第 1 頁，previous／next 依 server total 鎖定，並以 AbortController
及 request generation 防止較舊回應覆蓋新查詢；一般畫面不得顯示 cursor 或 fingerprint。此 query 固定
0 commit、0 receipt、0 outbox、0 provider call，也不變更人工審核 Preview／Apply owner。

#### Order group numbered observation query（2026-08-25）

React 三方群組清單使用 additive `GET /api/v1/line/order-groups/numbered`；事件歷程使用
`GET /api/v1/line/order-groups/{case_no}/events/numbered`。兩者只接受 positive `page`、bounded
`page_size`，清單另接受 closed `status`，並回 strict `items/page/page_size/total/total_pages`。
既有兩條 `limit` Query 保留為 compatibility projection，不改義或退役。

Numbered Query 必須由 repository `COUNT` 與 `LIMIT/OFFSET` 取得 server metadata，不得固定取首
200 筆群組、首 100 筆事件或在 React 假切片。篩選／群組切換回第 1 頁，previous／next 依 server
metadata 鎖定，AbortController 與 request generation 防止舊回應覆蓋。此 Query 固定唯讀、
0 commit／receipt／outbox／provider call；LINE Integration 不接管 Orders 案件根事實。

#### Notification Rule Administration（2026-08-20）

LINE Configuration 擁有通知規則 revision 與 closed grammar；LINE Notification 擁有 derived decision／intent，
LINE Delivery 擁有 delivery task。規則只接受已登錄 event、recipient selector、schedule、frequency 與 predicate；
未知 owner event 只能以 `enabled=false` 的 shadow 保存，不得啟用。空 genesis `{}` 在邊界明確 materialize 為
`{"rules":[]}`，不得讓 raw `dict` 穿透 dedicated public route。

Preview 固定零寫入並回 server fingerprint。Save／Delete 必須在單一 outer LINE UoW 內 fresh-read revision、
核對 preview fingerprint 與完整 command identity，依序保存新 configuration revision、鎖定並取消 removed／
enabled→disabled 規則的 scheduled intents、將 exact task IDs 交由 LINE Delivery owner 鎖定取消、append
idempotency receipt 與 audit，最後由唯一 commit owner commit。Repository 不得 hidden commit，Notification
repository 不得直接更新 delivery task，lock 順序固定 configuration → intent → task。

same key＋same canonical command 必須在 stale check 前回既有 receipt；same key＋different definition、actor、reason、
correlation、revision 或 preview fingerprint 固定 typed conflict。Receipt revision／counts、DB row shape/type 與
intent→task lineage 均 strict fail closed；不得以 coercion、去重或重算 fingerprint 隱藏 drift。HTTP command 本身
不得呼叫 provider或 wakeup；worker/provider 執行前仍需重讀 cancellation。Manual replay 會建立新 intent，
不屬於本契約，也不得因本節完成而開放 React 呼叫。

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

Rich Menu publication history 是唯讀、server-owned 的 numbered query；回應必須包含
`items`、`page`、`page_size`、`total` 與 `total_pages`。管理工作台不得先讀取固定首 N 筆再在
瀏覽器假分頁；切換頁碼必須重新向 server 查詢該頁，取消或較舊請求不得覆寫較新的頁面結果。
空歷程是合法業務空狀態，不能改以假資料、發布 mutation 或 provider 呼叫產生可翻頁案例。

- Menu definition、image digest 與 publication snapshot 不可在 processing 後被覆寫。
- Rich Menu 管理工作台必須允許具權限的管理員在尚未進入 `processing` 的 draft revision 調整背景圖
  與各熱區按鈕顯示名稱。背景圖以受控 media asset／digest 參照，按鈕名稱屬 menu definition；不得把
  base64、任意外部 URL 或 provider raw payload 寫入 definition。修改只建立新 draft revision，不得原地
  覆寫 published／processing snapshot，也不得在儲存草稿時直接呼叫 provider。
- uploaded 背景圖的 canonical reference 固定包含 `image_asset_id`、`image_asset_sha256` 與 opaque
  `image_asset_version`；不得接受 raw `image_path` 或只有 asset ID。Preview 以 owner-scoped metadata Query
  驗證 owner、digest、version、尺寸與刪除狀態且保持零寫入；Apply 只對新 command 在同一 outer
  transaction 重新鎖定 exact owner asset 並 fresh validation，任一 drift 在 audit／commit 前 fail closed。
  terminal replay 回原結果，不因之後的 asset 狀態改變而重做新 mutation。
- React 只顯示可理解的檔名、尺寸、載入／合法空狀態與不可選業務原因；不得顯示 digest、opaque version、
  storage locator 或 raw provider 欄位。選擇背景圖只改 browser-memory draft，仍須走 server Preview →
  明確確認 → Apply → committed readback。
- 背景或按鈕名稱變更後，工作台預覽必須立即投影同一 draft revision；既有按鈕 action、熱區座標與角色
  audience 不因改名自行變更。若操作者另行修改 action／座標／audience，必須走各自 typed contract，不能
  由前端猜測或與名稱修改綁成隱性 mutation。
- 2026-08-25 人工新增 action 編輯：Rich Menu 管理工作台的手機模擬器與編輯器必須讀取同一 draft
  revision 的 typed action，不得由按鈕名稱、順序或前端 hardcode 推導。管理員可在 closed action kind
  `uri | message | postback | richmenuswitch` 內修改各自允許欄位；LIFF URI 只接受 canonical target／runtime
  composition，literal URI、message text、postback data 與 alias 各自驗證長度、scheme／格式及互斥欄位。
  修改須建立新 draft revision 並走 zero-write Preview → 明確確認 → Apply → receipt/readback；processing／
  published snapshot 唯讀，儲存草稿不得直接呼叫 provider。`configurations/{kind}/safe` 仍禁止輸出 URI／
  action data；只有已認證 Rich Menu 管理工作台的專用 typed draft query 可取得編輯所需欄位。
- 本機互動預覽固定保留。它以 current server draft snapshot 加上尚未 Apply 的 browser-memory edits，立即
  重繪手機選單並模擬點擊結果；不得寫 DB、建立 receipt／delivery task／publication intent 或呼叫 LINE
  provider。本機預覽不能取代 server `PreviewRichMenuDefinitionChange`：操作者送出前仍須由 server zero-write
  Preview 驗證 normalized definition、revision、action 欄位與 blockers，再明確確認 Apply。Apply 成功後重新
  Query 的 persisted draft 必須和本機預覽一致；不一致時顯示 conflict 並禁止發布。
- `message` action 編輯器必須顯示並修改實際將由該按鈕送出的 message text；本機點擊只在手機模擬器
  顯示同一文字，不實際送出。切換 action kind 時必須清除前一 kind 不相容欄位，不能殘留 URI、message、
  postback data 或 alias。按鈕改名不得改 message text，message text 修改也不得改按鈕名稱；兩者只有在
  操作者分別編輯時才改變。
- 專用管理契約至少包含 `QueryRichMenuDraft`、`PreviewRichMenuDraftChange`、
  `ApplyRichMenuDraftChange` 與 committed draft readback。可重用既有 LINE Configuration owner／repository，
  但不得把 generic raw configuration endpoint 直接穿透 React；Apply 必須帶回並驗證 server Preview
  fingerprint、expected revision、reason、idempotency 與 correlation。相同 key／payload replay 回原 receipt，
  same key／different payload、stale revision 或 fingerprint mismatch 固定零寫入。
- `QueryRichMenuDraft` 與 committed readback 必須依 exact
  `(menu_definition_id, configuration_revision)` 投影 `editable | processing | published` 狀態及 closed
  業務原因。`publishing` 映射為 `processing`，同 revision 同 menu 若同時存在多筆則 `published`
  優先；舊 revision 不得鎖住 current draft。管理 UI 對 `processing／published` 不掛載草稿 mutation
  controls；缺 lock、revision／menu mismatch、未知狀態或缺業務原因固定 fail closed，不得讀歷程首筆、
  固定首 N 筆或由前端 hardcode 猜測可編輯性。
- 發布採 create／upload／link／switch／cleanup 的 saga，每一步保存 receipt。
- retry 從已確認 provider receipt 繼續，不重複建立資產。
- Rich Menu saga 的現行 additive persistence contract 由
  `line_rich_menu_publication_step_acknowledgements`、
  `line_rich_menu_publication_step_attempt_events` 與
  `line_rich_menu_publication_cleanup_anomalies` 保存 acknowledged step、typed provider outcome
  與 cleanup anomaly；三表均以 publication FK、request fingerprint、idempotency key 與 immutable
  update/delete guard 維持 replay／lost-ack 證據。既有 `line_rich_menu_publication_step_receipts` 保留為
  compatibility projection，Option B 不 alter、seed 或 backfill 該表。
- 身分綁定成功必須在同一交易 enqueue 個人 Rich Menu binding intent；worker 解析該身分角色
  最新已發布的 provider menu 後執行 link，identity binding 不因外部 API 暫時失敗而回滾。
- 新 Rich Menu publication 成功時，必須在記錄 published 的同一交易，依 menu audience role
  對全部 bound LINE identities fan-out 個人 binding intents。每筆 intent 以 publication ID 與
  LINE user ID 組成冪等 identity，並固定本次 provider menu ID；既有身分不需要解除或重複綁定。
- media／文件 bytes 依 `00` §2.2 保存於工會地端受控 NAS；DB 只保存 metadata、owner、opaque
  object reference、digest、size、content type 與版本，不保存大型 binary 或任意外部 URL 當永久根事實。
  LINE 只可依 owner 已提交的文件版本建立 durable delivery task；worker 發送前須重讀並核對 object
  identity／digest，缺失或漂移固定 fail closed，掃描到檔案本身不得觸發 provider 呼叫。
- 正式套用採單人流程：管理員先看到目前 menu snapshot 的預覽，再按「確認目前預覽」取得
  server-side preview receipt，最後勾選二次確認才可 Apply。Apply 必須鎖定同一管理員、
  同一 menu、同一 config revision 與 fingerprint；任一內容變更使舊預覽失效。沒有雙人覆核。

## 4. Domain：Access Control

### 4.1 正式內部使用者存取模型

2026-08-16 最新人工裁決：所有已登入且 enabled 的內部使用者具有相同業務功能權限。本系統不以
role、capability、職稱或部門限制內部使用者可操作的業務功能，也不採 fixed role bundle、dynamic
grant／revoke、階層比較或雙人權限覆核。root 與所有其他 enabled 帳號一樣可使用完整業務功能集合。
唯一額外權限是 Access Control 自身的帳號中心：恰有一個 enabled `root` 帳號可進入帳號中心並執行
帳號生命週期管理；此額外權限不是業務功能權限，也不得延伸為其他 API、UI 選單或 Domain 操作的
差異化授權。

- `AdminPrincipal` 是 human actor identity，用於 authentication、操作歸屬與 audit，不代表差異化權限。
- 業務 API 只判斷 session 是否有效且 user 是否 enabled；通過後可使用相同業務功能集合。
- `root` 是 Access Control root fact，不是可由一般帳號調整的 role 或 capability；僅 root 可讀寫帳號中心、
  建立帳號、啟停帳號、重設 credential／MFA 與撤銷其他帳號 session。root 不得停用、降級或移轉自身；
  root 遺失只能依受控離線維運程序復原，沒有 production HTTP break-glass endpoint。

- human authorization 不接受 `X-Legacy-Shared-Key` 或任何 legacy shared key。machine caller 在
  local/test 只可使用 `INTERNAL_SERVICE_SHARED_KEY`，production 只可使用已驗證且 caller allowlist
  通過的 Google-signed OIDC；兩者都不能冒充 human actor。
- body、query、UI session label 或任意 role／capability 字串不得成為 actor 或改變可用功能。
- UI 不顯示依人員而異的業務選單，也不建立「有權／無權角色」驗收案例。
- 外部 provider、production environment、secret、資料庫 target、SystemPrincipal 自動命令範圍及
  Preview／Confirm／Apply 等安全門禁不屬於人員差異化權限，仍須遵守各自契約。

Rich Menu 存取驗收狀態（2026-08-25）：authenticated、enabled 的 persisted `chris` Session 已由
Chrome 實點 server zero-write Preview 成功，未再因 `root` 名稱或 publisher capability 被拒絕。
publication queue 會在 commit 後 wake worker；依本輪不真實 push 裁決，queue readback 為 `not_run`，
不得以 local bypass、假 publication 或 API mutation 補驗。provider publication 仍由獨立 blocker 列管。

### 4.1.1 2026-08-20 live traceability note

正式 invariant 不變。`PROV-20260817-line-knowledge-authorization-normalization-work-package.md` 已取得
exact approval 並完成 `G0-G6`；Access/FastAPI、LINE compatibility projection、Knowledge route inventory 與
current regression evidence 已完成本包範圍的 live traceability。此完成不代表 Knowledge direct authorization、
provider、browser、deployment 或 React UI cutover；Knowledge direct authorization 維持 out-of-scope。

### 4.2 根事實與 state machine

根事實：

- admin user identity；
- password hash／credential version；
- enabled flag；
- root-account designation（恰有一個 enabled root）；
- encrypted TOTP factor、其 encryption key version 與最後成功 time-step；
- recovery-code hash 與 consumed fact；
- password challenge／MFA enrollment challenge 的 hash、綁定 account／credential／active factor identity／account access-control version、absolute expiry 與 single-use consumed fact；
- hashed login-attempt subject、rate-limit decision 與安全告警投影來源；
- hashed session token；
- issued、expires、last-seen、revoked time；
- security decision audit。

State：

```text
Admin user: enabled ↔ disabled（root 不可由線上 command 停用或降級）
TOTP factor: unbound → enrollment_pending → active → rotated | revoked
Password challenge: issued → consumed | expired
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
- `LoginAttemptPolicy`
- `PasswordChallengeIssuer`
- `TotpVerifier`／`TotpReplayGuard`
- `RecoveryCodeVerifier`

正式環境：

- internal key 缺設定 fail closed；
- Bearer session 必須存在、有效、未撤銷且 user enabled；
- 原始 token 只回傳一次，DB 只保存 hash；
- session 每次有效請求會滑動延長為 30 分鐘閒置期限，但首次登入起最多 8 小時；到達
  absolute deadline 後即使持續操作也必須重新輸入密碼。舊 session 缺少 absolute deadline
  時 fail closed；
- `APP_ENV=production` 禁止 auth bypass；
- development bypass 必須同時是允許環境＋顯式設定，並產生醒目 audit／startup warning。
- public login 固定兩段：Stage 1 只驗 username/password，成功僅簽發短效、single-use password
  challenge；Stage 2 驗該 challenge 與 TOTP 或 recovery code，成功後才建立 bearer session。任何
  Stage 1 未通過都回泛化 `invalid_credentials_or_factor`，Stage 2 failure 回泛化
  `invalid_credentials_or_factor` 或 rate-limit 429，不洩漏帳號、MFA state 或 factor 狀態。
- Stage 1 帳密驗證成功但 factor 尚未綁定時，屬成功的 `mfa_enrollment` challenge 結果，不是 403
  error；`POST /api/v1/admin/auth/login/challenges` 必須以 HTTP 200 `data` 回傳短效 challenge token、
  expiry 與 provisioning URI，且仍不得建立 bearer session。已綁定 factor 則回
  `factor_verification`；consumer 必須依 `challenge_type` 分支，未實作 enrollment 的 consumer 固定
  fail closed，不得把 enrollment challenge 當作一般 factor challenge。
- provisioning URI 與原 challenge token 只允許出現在帳密已驗證成功的短效 success `data` 及
  記憶體內綁定畫面；所有非 2xx error、URL、browser storage、log 與 audit detail 均禁止包含。
- password challenge 必須綁定 user、credential version、active factor identity、account access-control version、source-risk subject 與 absolute
  expiry；不得在 browser storage、log、audit detail 或 URL 保存 password、TOTP 或原 challenge token。

### 4.4 Subsystem：Account／Session Administration

Commands：

- `CreateAdminUser`
- `DisableAdminUser`
- `EnableAdminUser`
- `RevokeAdminSessions`
- `RotateAdminCredential`
- `ResetAdminMfa`

上述帳號／session administration commands 僅接受 root session；root identity、目標帳號與 expected
version 必須在同一 UoW 鎖定驗證。每個 Command 使用 expected version、authenticated actor、reason 與
idempotency key。本系統不採用 break-glass credential、緊急繞過 API 或自動復原流程。

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

### 4.8 Subsystem：Data Browser masked query

Data Browser只提供system admin對六個stable public source identities的bounded唯讀查詢；UI tab只是presentation，
不得把table literal升格為權威。canonical mapping固定為：

| UI tab | Public source identity | Cursor／row identity | Masked view |
|---|---|---|---|
| `orders_archive` | `orders` | `case_no` ascending／case number | status、service dates、updated time |
| `clients_archive` | `clients` | positive `id` ascending／decimal id | masked name、city、identity status、updated time |
| `staff_archive` | `staff` | positive `id` ascending／decimal id | masked name、city、status、updated time |
| `beclass_history` | `beclass_intake` | positive `id` ascending／decimal id | query number、masked name、received／updated time |
| `hcm_history` | `hcm_review` | positive `id` ascending／decimal id | masked case identity、issue codes、created time |
| `bank_facts_history` | `bank_facts` | positive `id` ascending／decimal id | dates/statuses；amount固定mask，不回帳號、交易人或fingerprint |

`GET /api/v1/admin/data-browser/sources/{source_id}`只接受上述enum，limit 1–100，cursor與query有界；unknown source
與invalid cursor在SQL前fail closed。list row本身即包含完整核准masked detail，因此本slice不新增detail GET。
columns/cells、row identity、source identity、version fingerprint與next cursor皆為strict typed fields；任何schema、
masking或identity drift使整個request失敗，不可回partial raw row。Query只執行stable-order SELECT，0 commit、0 mutation、
0 source-correction call；Global correlation boundary與typed 401／403／404／422／500涵蓋此route。

legacy raw table metadata與source-correction Preview／Apply不屬此query slice，仍保持not-ready；本契約不授權generic
PATCH、raw row、任意table／SQL、source repair或entry cutover。

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

### 5.2.1 Workbook atomicity／archive／recovery（2026-08-23人工確認）

- HCM Current採`WHOLE_WORKBOOK + archive_required`。原始workbook以content digest為immutable archive
  identity；archive寫入與完整性驗證失敗時Apply固定unavailable且0 Domain／DB write。archive成功後若
  outer transaction rollback，必須compensating delete；delete失敗建立operational anomaly，不得偽造成功。
- HCM來源若`exact IP + exact normalized name`命中既有Client，固定`review_only`：保存privacy-safe
  source review／receipt／outbox，0 Client／Order mutation，且不得同時建立partial case。合法HCM案件只因
  尚無唯一Client BeClass對方時，仍依既有lane建立Client／Order並讓`requires_cooking = NULL`；兩種情境不得混用。
- Client BeClass、Staff Historical、Historical Orders各採`ROW_ATOMIC_RESUMABLE + archive_required`。
  每個workbook必須有durable `running → row_committed* → terminal_receipt`與
  `retryable_interrupted | terminal_failed`；same key＋same canonical workbook只可replay terminal receipt
  或續跑未terminal rows，same key＋different workbook固定conflict。
- partial execution必須保存守恆aggregate、row terminal outcome、resume cursor及fresh target versions；UI
  不得把partial、job accepted或archive success顯示為whole-workbook匯入成功。
- archive只允許Case Import受控operator依稽核理由讀取；receipt不得含raw bytes、完整PII、原始檔名或local
  path。retention與encryption由Privacy／Operations擁有，期間及production provider在deployment target另行配置。
- 四 family 的 current successor 已具備 archive 與 `running → row_committed* → terminal_receipt`／
  resumable recovery，React 已完成 Preview → Apply → receipt → exact replay 的 runtime 驗收；此處原
  `DB_SCOPE_REQUIRED`／Apply disabled 敘述已由 `15` §15 的較新裁決取代。任何新 persistence 或 schema
  變更仍須另過 DB scope gate，不得由既有 runtime 驗收推定授權。

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
invalid row 必須保存 privacy-safe root fact；已滿足該 lane 最低 import 條件且需要人工處理時，
只產生 Case Import owner review。只有 `BECLASS-001`／`IMPORT-003` current pairing predicate
成立時才投影 canonical current issue。

HCM 不得以 fabricated default 補造欄位。案件編號是最低寫入資格：有可用案件編號時必須建立／保留
正式案件，其他欄位缺漏、格式錯誤或身份關聯歧義各自形成 owner validation／review result；只有案件編號
缺失或不可用時不建案，且只保留來源 review／receipt／outbox 稽核，不投影異常中心。
Client／Staff historical import 必須另走 HistoricalAdoption
Preview／Apply，不得重用 current LIFF command 假裝一般資料更新。

### 匯入 owner review 的外部確認與重新提交

HCM、Client／Staff BeClass 與其他 Case Import 來源的 review 是公會人員聯絡來源當事人的待辦，
不是管理端直接修正資料的表單。review root、處理狀態與 disposition 必須保留去敏資訊；不得持久化
LINE 對話原文、完整聯絡資料或把回覆文字直接當成正式 Client／Order／Staff input。正確資料由
新來源重新走 typed Preview／Apply。2026-08-15 WP95 進一步裁決：已建 HCM 案件的缺漏、無效欄位與
同案修正版一律提交完整修正來源，由 HCM owning resubmission Preview／Apply 採納通過驗證且屬
HCM 欄位權威的差異；不提供警示中心或 Streamlit 單欄編輯，也不得修改 immutable source。

WP77／WP92 將 HCM 與 Client BeClass 定義為可獨立存在的兩條 intake lane。HCM 案件編號不得重複；
IP＋姓名精確命中既有 Client、多候選或其他身份關聯歧義時，案件仍依案件編號建立，但不自動綁定 Client，
並建立獨立 link review 供外部確認。HCM 歷史過渡模式只要符合最低寫入資格，即直接寫入來源的可寫欄位，
不推定目前 DB 值較有效；無法寫入的個別欄位仍各自留在 owner review。

Client BeClass 的 `query_no` 只是來源流水號，不得作為客戶識別或案件編號。LIFF 啟用前的過渡匯入只在
姓名＋手機完全一致且唯一命中 Client，且案件候選唯一時綁定；零筆或多筆候選都保留來源並警示，不允許
人工在警示中心挑選。LIFF 啟用後由登入身分直接綁定，不再使用這組過渡條件。

Staff BeClass 歷史匯入以有效身分證及姓名為最低資格。後來的歷史快照覆蓋可更新 scalar，銀行帳戶與勾選
關聯視為完整集合原子替換；姓名改變可寫入並留下 owner source／receipt 追溯。任一其他欄位缺漏或格式無效
仍建立欄位級 owner review result。Staff 退役不由匯入推定或修改。

2026-08-25 管理端正規化資料投影：客戶資料只讀已採納的 `identity_status`、`city`、`service_type`、
`service_time`、`delivery_type`、`residence_type` typed facts；不得解析或顯示 raw `survey_details`、來源識別、
銀行資料或指紋。合法空值固定顯示「尚未登錄」，不得補預設值。月嫂名冊的服務能力欄位由第 `24` 份
正式規格 §3.3 擁有。此客戶投影已以 Chrome 驗證非空與合法空值，狀態為 `completed`。

有 HCM 而無唯一 Client BeClass 對方時投影 `BECLASS-001`；對方日後唯一綁定後由 root predicate 自動解除。

2026-08-29 current-state anomaly slimming 裁決取代舊的 field-warning occurrence／tracking
生命週期：新輸入缺漏或格式錯誤在 LIFF／backend validation 拒絕；既有或歷史錯誤
只存在 Case Import owner review Query。Case Import 仍保留來源、review、人工 disposition、
actor、reason、evidence、version、fingerprint 與 receipt 等 owner evidence，但 Anomalies 不另建或
保留 occurrence、warning task、tracking state、auto-resolve 或 replacement event。
只有 `BECLASS-001`／`IMPORT-003` 的 current pairing predicate 成立時進入 `#anomalies`；
owner 驗證後形成唯一、一致、可追溯的 accepted mapping，fresh recheck 才刪除 current row。
第一階段只記錄公會人工聯絡，不自動傳 LINE、不猜 recipient。
未登錄的 issue code 不得靜默略過或落入 generic field warning；投影交易必須回滾，只寫入
lane 與 issue digest 的去敏錯誤；總嘗試上限 3 次，相鄰嘗試至少間隔 1 秒，後進入
dead-letter，供維運先補 registry／映射再重放。retry-ready time 必須持久化，worker 重啟不得提早嘗試。

已知 validator 狀態不得被當成 unknown：Client BeClass 欄位 validation 以
`client_field_missing:<field_path>`／`client_field_invalid:<field_path>` 保存，兩者共用
`CLIENT-BECLASS-SOURCE-001`，由 display projection 區分「缺少欄位」與「格式錯誤」；不得保存錯誤
訊息中的原始值。HCM 既有案件收到不同 source fingerprint 使用 `HCM-CASE-002/$source_row`，缺案號仍
低於 import 門檻且零 warning。Historical Orders 的起／迄日不可解析分別使用
`ORDER-HIST-FIELD-001/actual_start_date|actual_end_date`。

live `ApplyBeClassReview`／`RejectCaseImportReview` 的 corrected-fields／Correct／Reject 形狀不是核准目標；
必須依 entrypoint governance 退役或替換為 owning Domain typed command；不新建 tracking-only
transition 作為 anomaly lifecycle。

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
- `ApplyCaseImport`／各 lane HistoricalAdoption Apply → 正式 root receipt、owner validation／review result 或 typed blocker
- `PreviewHcmResubmission`／`ApplyHcmResubmission` → 驗證完整修正來源、prior owner review 與 canonical
  case 的明確關聯，採納通過驗證的 HCM-owned fields；link 只有唯一可證明時建立
- owner review referral descriptor → 只回傳 owner command identifier、expected review version 與去敏 context

#### HCM resubmission owner-command amendment（2026-08-30 人工裁決）

- Client 必須有 versioned root，HCM 修正只能透過 dedicated typed
  `ClientHcmCorrectionCommand`；不建立 generic profile／root editor，不允許 Case Import adapter
  直接寫 `clients`。
- `服務方式` 是 Client root fact，canonical persistence 為 `clients.service_type`；Orders 不新增
  `service_type`。`end_date` 仍由 Orders terms／lifecycle 依其正式 root facts 衍生，Client correction
  不得直接寫入或重算它。
- canonical HCM review identity／version 完整取代 legacy warning occurrence／current-task identity；
  legacy association 只供 provenance read，不得成為新 Apply 的 mutation root。
- Preview 零寫入，`preview_fingerprint` 必須覆蓋 source、canonical review、Client、Orders
  與必要 downstream owner versions。Apply 依 canonical ordering fresh-lock 並重建 fingerprint，
  先查 replay，再透過 typed Client／Orders ports 執行 mutation。
- Orders 只能呼叫 `OrderTermsWorkflow.apply_in_current_uow`或等價正式 typed command；
  Client／Orders infrastructure adapters 只借用 caller connection，不得 commit、rollback 或建立
  nested Unit of Work。Case Import 是唯一 outer UoW，在同一 commit 寫入 accepted
  correction、Case Import receipt／event／outbox 與兩個 owner mutation。
- commit 後必須 fresh-read Client 與 Orders authoritative facts。任一步驟失敗整體 rollback；
  replay 不重複 mutation；stale owner version 零寫入；readback mismatch 回 typed
  reconciliation blocker，不得回報成功或盲目重試。
- Client version／event／receipt persistence 必須以 additive schema release 建立。本裁決只授權
  本機 schema／code／test package，不授權 production／`union_db`、backfill、deployment
  或刪除 legacy evidence。

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

警示中心人工入口只允許查詢去敏 current issue 及導向已核准的 owning Domain typed command；
不得使用 Data Browser、importer fallback、generic corrected payload 或 candidate picker 改正式資料。
異常頁不提供人工 `closed`。live `RejectCaseImportReview` 不得再作為正式入口；
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

- API／LINE／自動化與潛在狀態機歷史合併稿（已由本規格承接並自工作樹移除）
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

## 2026-08-21 Four-module specification amendment

### Identity／M1

`line_identity_bindings` 與 binding events 由 LINE Identity application 作唯一 writer；Case Import 擁有 `provisional_client_registrations` 的 provisional registration。LIFF onboarding 是 binding projection outcome，不是 role promotion；customer／staff／admin root facts 仍由各 Domain 擁有。legacy direct writers 必須 guarded／readonly 或 `410` 並逐 caller 退出。Customer Service 可提供 `binding_failed_assistance`，但 dual-role／two-failure escalation 由 M4 successor 處理；真實 LIFF／verified-token E2E 仍需 sandbox config，規格不宣稱 PASS。僅在 development／test 且 server 明確設定 `LIFF_REQUIRE_ID_TOKEN=false` 時，canonical registration page 可用受控 development LINE identity 完成同一 typed registration／binding UoW；LIFF runtime config 缺失本身不得在 production 或未提供受控 identity 時解鎖表單。

### M2 routing precedence

production full AI 現在 REJECT；Phase 1 只核准 deterministic harness＋durable manual fallback，Phase 2 維持 proposed。explicit human／wrong 優先於所有自動路由；只有不含 human／wrong marker、且 exact match protected identity alias 的輸入才可進 identity。Service Help 只建立 committed durable delivery task，不在 webhook transaction 直接呼叫 `reply_provider`。

webhook dispatch 任一業務處理失敗時，當次 business Unit of Work 必須整筆 rollback；rollback完成後才可
另開 Unit of Work 記錄本次 `retryable_failed`／`terminal_failed`。禁止留下部分 ticket、binding、outbox
或其他業務 mutation，也禁止讓失敗紀錄跟著原交易一起回滾。

### M3／M4 boundaries

Scheduling Matching Coordination 是 Scheduling subsystem；`accepted` 只進 fresh-effects check，產生 typed Assignment conversion/rematch request，LINE／Orders／Assignment／Payroll root writer 不被接管。M3 Phase D 只可透過 typed ports 整合 leave／assignment owner。Runtime target registration／reset／enable／disable 共用 0-schema advisory serialization boundary、active singleton、opaque CAS 與 same-key replay；lock failure 固定 0 write，commit 後 release unknown 不回 success 並以原 key 查 receipt。Customer Service 擁有 HIGH escalation；Anomaly 只作 source，escalation 不競寫 `runtime_alert_application`。

M3 的 service-date Apply 必須在單一 outer UoW 內 fresh-lock owner service dates、assignment與shifted-date availability後重算preview。leave Preview／Apply只讀Scheduling-owned immutable canonical receipt；Apply須在同一outer UoW重新讀取並把receipt identity、version與fingerprint綁入完整M3 source tuple。package／criteria／leave version／original staff／preview任一stale時，必須在M3 lineage、receipt與intent前rollback；M3不得藉此寫Leave、Orders、Assignment、Payroll或直接呼叫LINE provider。

本 amendment 的 initial freeze 不單獨授權 mutation；後續人工裁決已核准 M1-A、M2-A、M3-A～D、M4-A
的 exact production implementation slice。LINE／AI provider、deployment、production DB、未另行核准的
schema／DDL與 external side effect 仍不在授權範圍。
