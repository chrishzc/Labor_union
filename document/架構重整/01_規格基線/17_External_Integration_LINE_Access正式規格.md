# LINE、Access Control、Case Import 與 Knowledge 正式規格

> 2026-10-29 帳務參數裁決：Case Import 依規格04 §0 PRICE-01／02在正式案件首次建立時綁定適用政策，包含待補件；正式root初始化沿用綁定版本。新增身分沿既有三種規則明確映射；不得於查詢或重新匯入時改選最新版。名冊僅組合個案計價入口，不取得帳務writer ownership。\n


2026-10-21 管理端互動裁決：依 `00_Global_共同契約.md` §2.4，人工操作改為一次點擊送出、原因選填；本文件原管理端 human Preview／再次確認要求由該節取代。既有 LINE writer、revision、授權、冪等、outbox／task 與 provider terminal readback 邊界保持；公開 LINE／LIFF 使用者流程不變。

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
- 2026-10-22 人工裁決取消整個群組告警功能；先前登錄、同群重綁、重設與群組審核連結要求均退役。保留管理員個人通知與案件服務群組。

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
8. provider timeout／5xx 可 bounded retry，但不得覆蓋各操作的 uncertain-outcome 限制；
   LINE Reply 的不確定結果依第 20 份規格及本文件 §3.3，不可自動補送 Push 或重試回答。
   invalid signature、mapping ambiguity 與業務 blocker 不可自動猜測。
9. Domain decision audit 與 Domain mutation 同交易；HTTP access／diagnostic audit 可 best-effort，
   但不得冒充 Domain audit。

### 2.2 Provider-neutral ports

- `ExternalSignatureVerifier`
- `ExternalEventNormalizer`
- `DurableInboxRepository`
- `DurableDeliveryQueue`
- `ExternalEventConsumer`
- `DomainCommandGateway`
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

### 3.0 服務當天原群組通知

依規格 20 §6.8，`order.service_start_day` 只對正式開工當天的原服務群組產生單次即時通知，包含未結清第一期款提醒及當日月嫂服務狀況按鈕；已結清省略催款。明確 postback 驗證 current bound staff、原群組、正式日期及有效當日班表後，記錄回覆；協助需求交 Customer Service 既有待辦 writer。無管理員告警、一般群組對話監聽或服務／帳務事實變更。來源投影及回覆各沿既有 outer UoW，provider 僅由 committed task worker 呼叫。舊 `order.pre_start_reminder` 不再啟用、投影或重送，尚未發出的私人提醒取消。完整文案、按鈕、重播及 stale 行為見規格 20 §6.8。

第二期款依規格 20 §6.9，以 `client.second_payment_due`／`client.second_payment_settled` 投影原服務群組純文字通知；只接受原群組、即時、單次規則。到期當天仍欠款才提醒，已結清不催款，不需第二期／零金額／資料不足完全不觸發。成功通知只來自帶標記的 committed Finance `projection_refresh` 及有效核銷；送前 fresh-read 需求、金額、日期、群組及收款，失效取消。無群組走既有 LINE-006 待辦。舊前三日私訊來源／模板及未寄工作停用，歷史設定仍可讀但不可重新啟用；不補送歷史核銷、不發布選單。

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

#### 服務完工群組通知

規格 20 §5.6 的服務完工／滿意度問卷邀請只消費新提交且明確標記的 Orders completion outbox，透過現有 source／decision／intent 建立原案件群組的一次文字通知。問卷網址先留空，不建立空白網址按鈕；日後沿既有模板內容加入連結。provider 前複核完工證據、群組及版本，缺群組交既有內部處理，不私訊或補發歷史。此通知與身分選單恢復各自去重，不新增時段或完工關卡，不更動帳務，不直接呼叫 provider 或發布選單。

#### 服務開始提交、代班邀請與群組日期結果

服務中換人共用本節意願、單人邀請、current membership 與群組日期表投遞契約，業務詳規格 02「服務中換人」及規格 20 §5.2B。工會記錄交接日後委派既有正式 handover writer，日期表無確認按鈕；不監控聊天、不新建群組、不發額外私人通知。

業務流程由規格 02 SSTART-01～08 擁有。群組聊天不監控、不解析日期或同意；客戶不透過 LIFF 提交本流程日期申請。一般月嫂經 verified LIFF 主動提交接受與約定日期或不接受需代班；LINE 只驗證身分並轉交 Scheduling，不能自行寫 Orders／Scheduling／Finance roots。
正式日期與班表成功提交後，LINE 只消費 committed owner intent，對目前綁定的本案服務群組建立無「確認日期表／拒絕日期表」按鈕的日期結果紀錄。記錄含案件、實際開始日、各月嫂區段與服務日；不寄個別日期確認卡，不追問拒絕原因，不把 recipient 回覆或送達狀態作排班資格。舊卡片不再授權新變更，歷史 snapshot、回覆、receipt 保留不可變。delivery failure 不回滾正式結果、不再次執行排班或帳務。

代班例外先由工會選人詢問意願，不願意改問其他人；願意才經 Scheduling 的選定人選／替代區段授權，對該月嫂寄送本案原群組邀請。入群後由人員直接填實際服務日期；代班月嫂不用再開 LIFF 接受或填日期。邀請工作送出、provider 送達與 membership 加入是三種不同證據，不得互相推定。

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

2026-09-13 已有投遞契約的修正對照：Reply HTTP 5xx 本身不是「確定未接受」的證據；
不確定結果使用既有 `line_reply_outcome_uncertain`，禁止立即 Push 與自動重試該回答。
Push 的 retry key 不會對先前 Reply 去重；這不改變其他主動通知的既有 Push retry 契約。
PR #299 worker 改為逐筆取得即將執行任務的租約，保留每輪預設 25 筆；發送前檢查
相同、未過期 lease 與取消狀態，避免整批任務等待時共同耗盡租約。這是 source 行為，
不是對任意執行時間、MySQL 競爭或真實 provider 已完成驗收的宣告。

#### M4 Safe Review Link（2026-09-01 current Task96 contract）

M4 的 `Mobile_Group_Alert` 由 LINE Integration 擁有 review-link transport persistence；
`runtime_alert_application` 只擁有目前 active singleton target、target version 與 alert
source reference，Access Control 只提供既有 Admin Session／capability 驗證，不成為第二個
link writer。review link root 必須保存 opaque `review_link_id`、只保存 token digest、
canonical internal target identity、runtime target version、source alert identity、
allowed actor／capability、issued／expires／redeemed／revoked timestamps、root version、
correlation 與 idempotency identity；不得保存原 token、raw PII 或 arbitrary URL。

狀態固定為 `issued → redeemed | expired | revoked`，terminal 狀態不可復活。Typed contract
提供 `IssueSafeReviewLink`、`RedeemSafeReviewLink`、`RevokeSafeReviewLink` 與去敏
`QuerySafeReviewLink`；`Preview` 若由既有 owner surface 提供必須零寫入。Issue 在既有 LINE
outer Unit of Work 內 fresh-read alert target、保存 link root／receipt，並由 committed
notification intent／outbox 指向同一 canonical internal target；opaque one-time handle 只可
作既有同源 internal target 的受控 path projection，LINE payload 不得帶 raw token／PII、query／
fragment token、Bearer header 或 arbitrary URL。Redeem 必須鎖 link root，fresh-read target／version、已驗證 Admin Session、
actor 與 capability，成功只允許一次並追加 receipt；Revoke 由 runtime target owner 的
typed reference 觸發，同一 UoW 保存 revocation event／receipt。Delivery worker 只能使用
已提交 intent，不能在 HTTP 或 provider call 內建立 link。

失敗固定回 `safe_review_link_expired`、`safe_review_link_replayed`、
`safe_review_link_revoked`、`safe_review_link_wrong_actor`、
`safe_review_link_target_stale` 或 `safe_review_link_version_conflict`；錯誤不改 alert
root、不得盲目 retry。storage timeout／deadlock 可 bounded retry；actor、capability、
target 或 version 不一致必須 fail closed 並由 owner Query／人工 review reconcile。Readback
只回 masked target、link status、expiry／redeem／revoke outcome、root version、receipt 與
typed failure，不回 token／PII。若現有 persistence 無法承擔此 root，僅允許依 DB change gate
提出 additive schema；本節不授權新 public route、production／`union_db`、provider 或
deployment。

2026-09-13 source 對照：PR #299 的新 Issue 在同一 UoW 鎖定唯一 active runtime group，
將 owner `target_id`／opaque `current_version` 保存於既有 immutable `issued` event 的
`runtime_alert_target`；首次 Redeem 重讀該 evidence 與目前 owner facts。公開數字
`target_version`／`current_target_version` 的相等檢查不能代替這組 server-owned evidence，
也不代表已驗證 profile／assignment 等業務 root version。缺 evidence 的舊連結須重新簽發；
群組更換、停用或重新啟用後版本不同時拒絕首次兌換，exact command replay只回原receipt。
本修正未新增 schema。客服告警中的一般 mobile-admin URL 不是一次性 link，不能取代
第 26 份規格 §9／§9.1 的 alert → canonical review target → mobile failure/readback 驗收；
該完整鏈仍須直接證明，不能因本段 source 修正標為 passed 或 superseded。

#### 通知與發送：真實資料訊息預覽（2026-10-22 人工核准）

本次核准範圍為既有「通知與發送」整合工作台與 authenticated、zero-write 訊息預覽，不改 Domain roots、schema、正式投遞、部署或 provider 權限。此節同時界定本次 bounded implementation／驗收，完成後不另建平行規格或追蹤文件。

- LINE-PREVIEW-01：通知文案與訊息卡片共用清單，支援搜尋與文字／卡片篩選；內容編輯、既有發送設定與手機預覽置於同一工作台。文案框預設高度 504px，依 2026-10-22 後續人工裁決將實作的 252px 再加高一倍；手機預覽只保留一般手機，移除窄螢幕模式。
- LINE-PREVIEW-02：依 2026-10-22 最新人工裁決，通知工作台改用明確標示的公版範例，移除案件／月嫂選擇與資格限制。範例不得標示為真實案件、正式金額、日期或已完成的業務結果；不查詢真實對象以補齊公版。固定文案不要求業務對象。
- LINE-PREVIEW-03：`GET /api/v1/line/message-previews/catalog` 提供明列的正式訊息與純內容卡片入口。`POST .../preview` 增加 closed `data_source: sample | record`（既有呼叫預設 record）；工作台一律傳 sample，接受選用的 browser-memory 文案但不保存。既有 `GET .../subjects` 與 record 預覽維持原契約，不再由工作台呼叫。所有入口要求 `line.config.read`，回應 `Cache-Control: no-store`。
- LINE-PREVIEW-04：公版透過獨立、無 DB／writer／provider 能力的 typed sample port 提供案例、月嫂、請假、付款、候選與完整確認包範例，重用原純卡片組裝。公版結果逐項列出真正帶入的欄位中文名稱、變數／欄位路徑與值；文字只列使用到的變數，卡片列出其動態內容。公版不代表正式資格或真實財務結果。既有 record port 仍使用 readonly transaction 與原 owner Query，不改根事實。
- LINE-PREVIEW-05：重用正式文字範本與純卡片組裝函式，手機 renderer 只接受 closed display model。postback、interaction token、recipient identity、正式 URI 與 provider payload 不得穿透畫面；按鈕點擊只顯示動作說明。預覽不建立憑證、task、receipt、audit mutation、outbox／source event，不 commit、不 wakeup、不呼叫 provider。
- LINE-PREVIEW-06：公版不因未選案件或缺少符合資格資料而 unavailable；無效文案仍回 typed 422，訊息不存在回 typed 404、設定查詢失敗回 closed 503。使用者清空工會草稿時提示輸入，不冒充成功。record 呼叫維持 needs_subject／unavailable／not_found。前端以 cancellation／request generation 防止晚到結果覆蓋新文案，失敗不顯示舊欄位或舊預覽。
- LINE-PREVIEW-07：既有文案儲存與規則異動仍走原 owner、授權、revision 與回讀，不新增發送操作。驗收包含公版不呼叫真實對象 reader、欄位／值與渲染一致、所有目前正式訊息及卡片可直接預覽、去除可執行 action、原儲存回歸、晚到查詢防護、桌面／手機實際畫面及 build。測試與 source 歸屬沿用 notification-rules-presentation module。
- LINE-PREVIEW-08：依 2026-10-22 人工裁決，清單補列 current 身分／登記模板、服務與問答及訂單異動導覽、客服受理／結案、身分受理／完成、候選聯絡資訊一／二／每週服務說明、工會詢問／回覆及客戶完整推薦確認包。來源採明列的正式入口，不以所有 bootstrap 模板自動升格為現行訊息；D+1～D+3、未具正式用途的測試／baseline 模板均不加入。公版完整確認包與候選卡使用明列的範例欄位，不受現行正式方案或候選資格限制；既有 record API 仍只查所選對象的 owner 唯讀 projection，不鎖資料、不發履歷下載憑證。`allows_draft` 只對工會詢問／回覆卡開放 browser-memory 文案，畫面不提供儲存或發送；其餘補列訊息為唯讀預覽。

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

React 案件群組清單使用 additive `GET /api/v1/line/order-groups/numbered`；事件歷程使用
`GET /api/v1/line/order-groups/{case_no}/events/numbered`。兩者只接受 positive `page`、bounded
`page_size`，清單另接受 closed `status`，並回 strict `items/page/page_size/total/total_pages`。
既有兩條 `limit` Query 保留為 compatibility projection，不改義或退役。

Numbered Query 必須由 repository `COUNT` 與 `LIMIT/OFFSET` 取得 server metadata，不得固定取首
200 筆群組、首 100 筆事件或在 React 假切片。篩選／群組切換回第 1 頁，previous／next 依 server
metadata 鎖定，AbortController 與 request generation 防止舊回應覆蓋。此 Query 固定唯讀、
0 commit／receipt／outbox／provider call；LINE Integration 不接管 Orders 案件根事實。

#### Order group observation workspace（2026-10-16 人工裁決）

依使用者核准的精簡預覽，管理端案件群組使用 additive
`GET /api/v1/line/order-groups/workspace/numbered`、`GET /api/v1/line/order-groups/workspace/{case_no}`
及 `GET /api/v1/line/order-groups/workspace/{case_no}/events/numbered`。
清單支援長度不超過 50 的案件編號字面包含搜尋、closed status 與 bounded server 分頁，先列需要處理，再依更新時間排序；不是未建群案件的完整待辦。

工會 LINE 待辦工作台另提供「尚未建群」唯讀分頁清單：僅列正常未結案案件中，正式訂金
`settlement_state='settled'`、訂金金額大於零，且尚無服務群組綁定的案件。未核銷、只有付款留言／
銀行待處理流水、已取消、已完成、歷史案件及已綁定群組均不列入。不新增客戶簽約門檻或 LINE 綁定門檻；
既有建群／邀請指令仍各自驗證核銷及收件者身分。客戶簽約前可已有合法訂金核銷，不能由已付推定已簽。
新端點 `POST /api/v1/line/mobile-admin/order-group-todos` 只接受 server-verified 工會 LINE 身分及
`ORDER_GROUP_READ`，Query 零 commit／receipt／outbox／provider call，僅回案號、已核銷訂金金額及分頁數。
「複製設定格式」只複製 `綁定訂單 {case_no} 〈本群組邀請網址〉`；人員先換成實際網址，再貼到服務群組。複製本身不綁定或發邀請。
正式綁定完成後，重新查詢即移出待辦；核銷撤銷或案件取消亦不再列入。
所有舊 limit／numbered／detail Query 保持原契約。新 Query 沿用 `ORDER_GROUP_READ` 授權，固定零寫入、零 commit／receipt／outbox／provider call，不改綁定、邀請、狀態 writer 或 schema。

清單與側欄只提供必要姓名、原綁定狀態、最近事件、目前綁定時間、目前群組的最近邀請排入時間及客戶／指派月嫂加入狀況。成員來源沿用 Orders 目前客戶與指派 audience，另由 Scheduling 提供本案已選定、已表達願意的代班月嫂之受限邀請授權與區段；LINE 身分須由 canonical role binding 與 owner projection 一致確認；失配標記無法確認。加入／離開以目前群組綁定版本後已收到的 membership 事件為證據，不沿用先前群組的 joined 投影，不視為即時完整群組名單，也不判定工會幹部是否全部到齊。新工作區不輸出群組 ID、LINE user ID、actor ID、邀請原文或指紋。

不同來源歷程使用 `binding:<id>`／`runtime:<id>` 唯一事件鍵並依 server 分頁，英文事件代碼由 presentation 轉成中文；未知事件保留中性說明，不假推斷成功／失敗。邀請排入不等於 provider 已送達或成員已加入。群組觀察網頁僅查詢；一般綁定與全體邀請由已授權人員在 LINE 群組內操作，代班專用邀請由工會代班工作面沿下述受限授權發起；需正式訂金核銷與既有身分資格。其他 LINE 工作區不變。

#### 服務群組設定與邀請指令

已綁定 LINE 且具 `ORDER_GROUP_BIND` 的工會人員，在服務群組輸入
`綁定訂單 案件編號 邀請網址`，例如 `綁定訂單 115000157 https://line.me/R/ti/g/xxxxx`。
三段之間可用一般空白、多個空白、全形空白或換行；網址自身必須完整、不得拆行。
只接受無額外參數的 `https://line.me/ti/g/...` 或 `https://line.me/R/ti/g/...` 群組邀請網址。
格式檢查不能驗證連結是否仍有效、是否屬於本群組；網址由人員在本群組複製與確認，不由 Messaging API 取得。

設定須通過目前工會身分、案件、正式訂金已核銷及客戶／指派月嫂身分資格檢查。
綁定與網址在同一 outer UoW 保存；回覆「已設定案件 {case_no} 的服務群組。」。
設定不寄送私人邀請。相同群組／相同案件重輸新網址只更新網址，不清除成員紀錄或增加假綁定版本。
現有綁定的網址保持 NULL，直到人員輸入完整設定指令；不得從歷史投遞內容回填。

之後在同一群組只輸入 `發送邀請`，系統讀取保存網址、重新檢查資格後，
在同一交易排入媽媽與目前已綁定指派月嫂的私人邀請工作，無第二次確認。
群組回覆「訂單 {case_no} 的邀請已排入發送，共 {count} 位。」。
私人卡片：「服務群組邀請」「案件編號：{case_no}」「媽媽／月嫂您好，請點下方按鈕加入本案服務群組。」；
按鈕「加入服務群組」開啟保存網址。排入不等於送達或已加入。
發送前重新核對目前群組、網址、核銷與收件者；有變動即取消舊工作，需人員重新輸入發送指令。

缺案號、缺網址、無分隔、網址拆行、多餘內容或不合格式的網址，回覆對應簡短原因並附正確三段格式；不寫入設定或建立邀請。
尚未設定時提示先完成設定。邀請指令帶參數及舊式指令一律提示目前用法，不沿用舊式發送路徑。
未授權、未核銷或身分未就緒保留既有業務錯誤提示。未預期保存失敗交由 consumer 回滾，不回覆成功。
邀請網址僅供群組命令與發送工作內部使用，不出現在管理 Query、audit 或 repr；送達／失敗／過期後仍依既有規則遮蔽 delivery payload。
持久化為既有 `line_order_group_bindings` 的 nullable 私有 `invitation_url` 欄位，無新業務狀態、無業務資料回填。

#### 代班月嫂單人邀請

代班工作面只可對本案「人員已選定且該月嫂已願意」的人選寄邀請，重用保存的原群組網址、目前綁定與 canonical staff identity。Scheduling 提供 case／原區段／selected staff／意願版本的 typed 授權；一般候選池願意不能單獨取得入群資格。收件人限該代班月嫂，不重新邀請全案成員，也不先建立正式 assignment。撤回、改選、群組／網址／身分或意願授權失效時，舊未送出工作依 delivery 前 fresh 驗證取消。
工會手機與 React 代班工作面必須有「寄送本案群組邀請連結」操作，點擊即透過經授權的 typed command 建立選定一人的 committed delivery，無再次確認視窗；不能只提供唯讀狀態或要求人員回群組輸入全體邀請指令。按鈕及 server command 都核對 selected staff／願意回覆／本案區段／群組網址，回讀分開呈現排入、投遞與加入；提供重新查詢加入狀態。具體畫面／API 對照依規格 02「前端畫面與按鈕逐項對照」。
此入口不改一般 `發送邀請` 指令的全體收件語意。membership 使用目前群組綁定後的同一月嫂加入證據；人員工作面顯示待加入／已加入及投遞失敗，不能以「邀請已排入」解鎖加入完成。加入本身不代表正式指派；加入後由工會保存日期，成功後再對原群組寄日期結果表。邀請網址不輸出至一般管理 Query、audit 或 repr。

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

#### LINE-006 current-fact readback 與 manual replay terminal predicate（2026-08-31）

`LINE-006`的公開subject固定為`case_no + notification_reason`。LINE Notification擁有notification
source、decision／intent、`manual-replay:{source_event_id}:{idempotency_key}` immutable successor
lineage與source applicability interpretation；LINE Delivery繼續擁有task、attempt、retry與terminal
delivery result。LINE Integration只以typed、zero-write readback組合這些既有facts，不新增LINE-006
aggregate table，也不把Delivery root或terminal success搬入Notification。

同一subject是一個logical current group，可含多筆source／decision；只有Notification owner可證明
currently applicable的failed source參與predicate。合法cancelled、obsolete、superseded或不再適用的
source不需重送；無法完整判定applicability、lineage或delivery outcome時readback固定
`authoritative_complete=false`並fail closed。typed readback至少包含case、reason、owner snapshot
token／version、complete flag、applicable／unresolved source counts、closed unresolved reason codes與
`predicate_active`，不得輸出raw recipient、payload、message body、credential或完整delivery error。

每筆currently-applicable failed source必須以exact original source ID找到目前lineage中的manual replay
successor；replay建立新immutable source，原source不改寫、不新增`superseded_by`欄位。
recipient binding或configuration修正本身不解除predicate，只讓新的manual replay可執行。建立intent且
provider送出前都必須fresh驗證exact recipient、current binding、required notification configuration與
source applicability；intent／task保存當時rule／template／recipient snapshot。terminal delivery success
後，後續正常configuration revision不得回溯使該success失效，除非receipt／lineage被證明不合法或形成
新的currently-applicable failure。

`predicate_active=true`當且僅當complete current source set中至少一筆applicable failure沒有合格terminal
successor。missing successor、pending／processing／retryable、terminal failed、outcome unknown、ambiguous
lineage、fresh validation failure或owner readback incomplete／unavailable都不得解除；沒有applicable failed
source時predicate為false。Notification／Delivery相關mutation在既有outer UoW／outbox邊界內追加既有
`anomaly.recheck` intent；不得建立另一套replay、remediation或escalation framework。

通知事項與工會待辦 LIFF 沿此唯讀契約顯示建立前受阻的通知，typed readback 可提供確切未排除 source IDs 及其中排送中的 IDs，及經 exact lineage 核對的相關 task IDs，供原補送入口定位、去重及保留原工作處理。補送以原 source domain 的規則／收件資格解析，persisted successor 仍為 manual_replay，不把案件群組改套舊群組條件。此為既有事件衍生值，不建立新通知狀態。相關 task IDs 同時依 exact original source ID 分組，原工作只限制同一來源的補送，不阻擋同案其他來源。原案件取消或成為歷史案件時不再視為目前適用的服務通知來源；第二期款與完工通知的 applicability 重用各來源現行業務複核，不以收件人、模板或排程設定錯誤當作來源已失效。補送排隊、處理中、等待重試都不等於 terminal success。

### 3.4 Subsystem：LINE Identity／Review

State：

```text
Friend: unknown → active ↔ blocked
Review: pending → approved | rejected | cancelled
```

2026-09-13 好友事件修正對照：`follow`／`unfollow` 是使用者與官方帳號的好友狀態事件，
不是私人好友聊天。晚到且發生時間早於 `last_event_at` 的事件仍保留事件及版本紀錄，
但不倒退 canonical／legacy 好友狀態。舊 follow 不新建歡迎通知或綁定 flow，舊 unfollow
不取消目前通知；一般 message 不因時間較舊而被丟棄。event id 去重不能取代不同事件的時間判斷。

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
  published snapshot 唯讀；管理員可由其對應的 current configuration 內容建立下一個 draft revision，
  不得因 current revision 已發布就卸載草稿 mutation controls。儲存草稿不得直接呼叫 provider。
  `configurations/{kind}/safe` 仍禁止輸出 URI／
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
  優先；舊 revision 不得鎖住 current draft。管理 UI 對 `processing` 不掛載草稿 mutation controls；
  `published` 只表示該 revision 的 publication snapshot 已固定，仍須掛載建立下一版草稿的 controls，
  Apply 會建立新 revision 而不得覆寫該 snapshot。缺 lock、revision／menu mismatch、未知狀態或缺業務原因固定 fail closed，不得讀歷程首筆、
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

#### 2026-10-19 NAS 部署權限裁決（優先於下方舊部署認證敘述）

Authority：使用者核准本次最終權限清單並授權實作、設定與依序驗證；不包含真實 NAS 部署、Docker Hub push、LINE provider 發送或既有資料重建。

- NAS-AUTH-01：保留所有 enabled 內部人員相同業務功能與唯一 root 帳號中心。合法假日刪除、資格／偏好移除、匯入替換、虛擬帳號替換、排班替換、異常投影重查、封存及知識清理均保留；不以停用功能或一律 soft delete 取代。
- NAS-DB-01：日常執行帳號無直接 DELETE、DDL、GRANT OPTION、CREATE USER。刪除只透過用途固定、目標受限的 P01–P10 程序；EXECUTE 必須逐程序授權。DEFINER 為不可登入、僅持必要資料操作權的專用帳號，非 root。程序不接收 SQL／table name，不自行 COMMIT／ROLLBACK，caller 保持唯一 outer UoW。
- NAS-DB-02：P01 日期；P02 指定 staff 的資格／交通差異；P03 六項固定關聯；P04 指定 staff 的偏好集合；P05 依既有來源判定的 staff 歷史替換；P06 指定案件與舊 mapping 集合；P07 指定案件的被替換排班世代；P08 已由 owner fresh recheck 判定失效的 issue；P09 已封存且符合既有期限的 audit；P10 符合既有狀態、版本、期限／capacity Preview 的 knowledge target。程序限制不取代 typed owner 業務驗證。重播、stale、跨對象、交易失敗不得放寬既有契約。
- NAS-DB-03：管理／LINE 對外／維運作業以不同權限連線；LINE 不持 P01–P10 或管理憑證。欄位權限不得被舊的整庫 grant 覆蓋。既有資料保存、fresh bootstrap、upgrade、backup／restore 分別驗證，不重寫已發布 schema artifacts。
- 既有 `SELECT ... FOR UPDATE` 的 MySQL 執行前提：四個 runtime profile 與 locked definer 僅在本專案 database scope 持 `LOCK TABLES`，維持原本 row-lock／outer UoW，不以增加核心 UPDATE 或直接 DELETE 解決鎖定讀取授權。database 名稱的底線依 partial_revokes 設定正確處理，不能擴成其他庫的 pattern；鎖定權本身不增加業務寫入欄位。依據為 MySQL 8.0 官方 locking-read／GRANT 契約，實際 grant 仍須 engine 驗證。
- NAS-WORKER-01：NAS production 使用 `nas_service_token`；每個 Worker 獨立隨機憑證，API 由憑證對應驗證後的 service identity，不能藉 X-Internal-Service-Name 或 body 冒充另一服務。API 只保存 verifier；Worker 只掛載自己的憑證及 CA，不取得 DB credential。Google OIDC 不再是此部署認證路徑。
- NAS-WORKER-02：私人操作只在隔離網路提供 HTTPS，Worker 驗證 server 憑證；缺憑證、未知／撤銷 token、錯服務、明文連線皆 fail closed。初始化準備憑證，不新增人員啟用碼。既有 local development shared-key 工作流限 local/test，不能 fallback 成 production。
- NAS-LINE-01：LINE token 於後端驗證，再核對 current bound identity 與本人案件／assignment/day。需求表單先保存完整申請，工會核准才建立 Client／BeClass 與完成對應 binding；同筆申請重複核准不得建立重複客戶。既有已建立客戶不回退成待審。
- NAS-LINE-02：異動申請仍只寫 Customer Service intake；正式核心異動由工會與既有 owner writer 執行。日誌／照片保留本人有效服務範圍直接提交，不增加逐筆工會核准。
- NAS-LINE-03（2026-10-22 人工裁決）：取消群組告警及其分類模擬、登錄、重新啟用、重設與群組審核連結。管理端只顯示管理員個人通知對象，保留既有個人通知 Query／Preview／Apply；分類仍使用固定規則，不新增偏好表。舊群組入口明確拒絕，歷史工作不得繼續送往告警群組。客服受理／工單／hold、管理員個人通知、案件服務群組綁定與私人邀請不受影響。
- NAS-LINE-04（2026-10-19 使用者核准私人照片方案，後端先行）：NAS LINE composition 的日誌照片上傳、日誌 Query／Preview／Apply 只經受限私人 HTTPS 代理，不能 fallback 本機檔案 workflow；對外 URL、typed response、idempotency key 與 Scheduling outer UoW 保留。私人入口為 `/internal/v1/line-media/`，獨立 `line-media-proxy` 機器憑證只可執行此入口，不可執行其他 Worker 操作。私人端必須重新驗證原始 LINE ID token、current binding 與 assignment／service-day；僅 flow 或宣稱的 staff／LINE ID 不構成此入口的身份證明。保留本人直接提交，不增加人工核准。私人 API 不提供任意路徑、列目錄、覆寫或刪除操作；受控檔案格式與 DB schema 不變，正式檔案根目錄由可信後端持有。LINE 原有專用媒體流程保留。現行 LIFF 日誌頁直接送出並提供照片選檔預覽及本人附件查看／下載；部署 UID／ACL／掛載仍由 NAS 部署契約負責，不因本機介面驗證變更。

- NAS-LINE-04 的資料庫邊界：公開 LINE profile 對 controlled-file staging／objects／receipts／finalize／lease／reference／cleanup／reconciliation 及日誌主檔／附件／完成事件僅 SELECT，不可直接 INSERT／UPDATE；私人管理後端保留原受限 management profile 的合法 writer。原 LINE 通知 outbox／checkpoint、LINE 專用媒體及其他既有功能權限不變；不加寬任何 DB 權限，不新增表。
- 本人附件下載：`POST /api/v1/line/staff-self-service/service-day-logs/{log_id}/photos/{file_id}/download` 保留 LINE token 在 body；私人對應路徑為 `/internal/v1/line-media/service-day-logs/{log_id}/photos/{file_id}/download`。先查本人日誌，限制 file_id 為該日誌已保存附件且屬 Scheduling／相同案件／寶寶或餐食照片，再經原 controlled-file digest-verified download 讀取；未授權／不相關檔案皆不得開檔。只回 JPEG／PNG，private no-store／nosniff；不提供任意檔案下載、公開 URL 或 token query。前端以 authenticated fetch／Blob 顯示及下載本人已提交照片。

驗收對照：上述每一契約均需包含合法成功與邊界拒絕。DB 必須在 local disposable MySQL 驗直接刪除／DDL 拒絕、授權程序成功、錯目標與 stale 拒絕及 outer rollback；Worker 必須驗各服務隔離、HTTPS／CA、撤銷與不攜 DB credential。NAS 與 provider 未執行不得宣稱通過。

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
  local/test 可使用 `INTERNAL_SERVICE_SHARED_KEY`；本次 NAS production 依 NAS-WORKER-01/02
  使用 HTTPS 與逐服務獨立機器憑證。machine identity 不能冒充 human actor。
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
- 管理帳號建立（含 root bootstrap）及密碼重設的最低密碼長度為 10 個字元；既有密碼 hash 與登入驗證不需重建。此最低長度依 2026-09-10 人工指示調整，不改動 MFA 或 root 權限要求；
- Bearer session 必須存在、有效、未撤銷且 user enabled；
- 原始 token 只回傳一次，DB 只保存 hash；
- session 不設閒置期限；有效請求只保留其既有 absolute deadline，首次登入起最多 8 小時；到達
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

#### 4.3.1 NAS 首次安裝的網頁 bootstrap（2026-10-16 使用者修正範圍）

- 使用者明確要求 NAS 映像開啟管理介面後，直接以網頁建立第一個 root，免除 SSH／容器終端機。此入口只掛載於 NAS 管理測試 factory，不加入標準 `api.main`；部署邊界與驗收見 `deployment/nas-test/README.web-setup.md`。
- `GET /setup` 與 `GET /api/v1/admin/setup` 提供首次安裝畫面／是否需要設定；`POST /api/v1/admin/setup` 保留 HTTPS 與尚未存在 root 的 fresh fact，提交來源需與目前請求的 HTTPS 入口一致。不要求部署啟用碼或預填固定網站網址。使用者已要求移除額外啟用碼與網址設定；它們先前由實作者選定，不視為原始人工需求。
- 使用者明確決定先保留既有 HTTPS 限制；NAS 已確認支援 HTTPS，但網站憑證、專案入口與反向代理仍待確認，不包含於本輪變更，不以本輪打包代表 NAS 網頁已可直接存取。
- 寫入只能委派既有 `bootstrap_root_admin`，使用原本唯一 root designation 與 outer transaction／audit。root 已存在時拒絕建立或覆寫；concurrent bootstrap 只能有一個成功，競爭／deadlock 回 typed 409，不做 blind retry。不新增 table、root owner 或 reset／recovery HTTP endpoint。
- NAS 安裝表單沿用共用 10 字元最低密碼政策，傳輸上限仍為 256 字元。成功建立不簽發 session、不替使用者啟用 factor；後續仍走既有兩段登入與 MFA enrollment。
- password 不得出現在 validation error、browser storage、URL、log 或 audit detail。root designation 存在後關閉建立入口，重新啟動／重新下載映像不重開設定，也不變更帳號或 MFA。

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

Data Browser只提供system admin對六個stable public source identities的bounded唯讀相容查詢；自2026-09-11
起不再是canonical React日常入口，`#data-browser`依第33份正式規格導向案件中心客戶名冊。既有archive query
仍不得成為writer；UI tab只是legacy presentation evidence，
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

legacy raw table metadata與source-correction Preview／Apply維持退役；本契約不授權generic PATCH、raw row、
任意table／SQL或source repair。canonical名冊entry、欄位owner路由與cutover以第33份正式規格為準。

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

<a id="noncitizen-intake-20261029"></a>

### 5.1.1 非市民案件申請與建案（2026-10-29 人工確認）

狀態：`implemented / repository-local-verified`。使用者已於 2026-10-29 核准七階段實作與逐階段驗收；執行範圍及實際證據見 [非市民案件實作工作包](../非市民案件實作工作包.md)。此狀態不代表已部署、使用正式資料或完成外部 provider 驗收。

本節是非市民進件與配號的正式 owner 契約；付款及帳號公式由 `04`、訂單推進由 `01`、契約由 `21`、統計由 `15`、LINE 導流及頁面設定由 `29`／`20` 承接。非市民與補助案件共用既有 owning-domain commands，不另建一套訂單生命週期或帳務 writer。

- **NC-ENTRY-01**：非市民新案由 LINE 官方帳號的 LIFF 表單提出，不由 HCM 匯入建案。HCM 與 BeClass 在此是欄位格式來源，申請人以一張表單提供合併資料，重複欄位只填一次。
- **NC-FORM-01**：非市民表單的 HCM 欄位全部必填，BeClass 欄位維持既有必填規則；同一欄位同時來自兩者時須滿足 HCM 必填要求。此裁決只約束非市民新表單，不改變補助案件 HCM workbook 或既有 BeClass 問卷的驗證規則。案件編號仍是核准後由系統配發的欄位，不要求申請人填入尚不存在的編號。
- **NC-FORM-02**：原 BeClass「補助款退款帳戶」保留銀行、分行與銀行帳號，改稱「退款帳戶」，供非市民一般退款使用；必填與否仍依 BeClass 原有規則。資料只交既有欄位 owner 保存及供授權退款作業使用。
- **NC-APPROVAL-01**：送出只保存完整待審申請及既有 receipt，不建立正式案件或預先配發案件編號。工會核准後才建立 Client／BeClass 及 Orders 案件並完成相應 LINE binding；畫面需區分申請編號與正式案件編號。
- **NC-APPROVAL-02**：核准沿用既有 application outer Unit of Work，委派各 owner 建立正式資料及綁定適用非市民費率政策。重複核准回原結果；同年度並行核准不得配出相同案件編號，失敗不得留下半套正式案件。這是既有交易／冪等要求在新進件類別上的適用，不新增獨立 commit owner。
- **NC-NUMBER-01**：案件編號格式為 `A＋民國年度＋3 碼流水號`，年度依工會核准建案日（臺灣時間）判定，各年度從 `001` 開始。例如 115 年依序為 `A115001`、`A115002`；年底申請而 116 年核准者使用 `A116001` 起的年度序列。
- **NC-NUMBER-02**：非市民虛擬帳號末三碼為案件流水號加 `500`，故 `A115001 → 501`、`A115002 → 502`；此號段分界依使用者提供「補助案件不會超過 500 件」的業務前提區隔兩類案件。其餘帳號組成及對照優先序由 `04` §8 擁有。編號容量與超量處理依使用者裁決暫不納入本次範圍，不將三碼可表示範圍另行升格為已確認的案件容量政策。
- **NC-FLOW-01**：正式建案且資料齊備後，候選月嫂、詢問意願、意願回覆、客戶推薦確認、外部契約簽署、定金核銷、服務日期與排班、履約、完工及兩端結算均沿用既有流程，完整逐步對照見 `01` §3.1.4。
- **NC-PAYMENT-01**：套用現有非市民費率政策及契約自費條文，定金按 5 天服務費收取，剩餘服務費分期金額與繳款期限沿用既有計算公式，詳 `04` §0.1 及 `21` §1.2。
- **NC-STAT-01**：非市民排除於既有案件受理統計，另以工會核准建案日提供獨立案件統計；帳務統計則提供補助案件／非市民案件／全部案件篩選。完整計數及篩選契約分別見 `15` §15.3、`04` §0.1。

### 5.1.2 後續實作影響範圍：LIFF、管理 UI 與資料邊界

下表是已確認需求的實作影響清單，現有路徑僅用於定位。表中任何項目均不得據此宣稱已實作或已驗收。影響清單由本節維護；使用者後續已核准七階段實作與逐階段驗收，進度及實際結果統一記於 [非市民案件實作工作包](../非市民案件實作工作包.md)，本節仍是業務契約權威。

| 畫面／邊界 | 現行定位 | 後續需調整內容 |
|---|---|---|
| LIFF 客戶登記導流 | `line/static/gateway.html`、`29` §4 | 保留已申請／未申請市府平台分流，新增「非市民服務申請」選項，直接進入非市民填寫頁，不要求先完成市府申請 |
| 新增非市民 LIFF 填寫頁 | 現有 `line/static/register.html`、registration typed transport | 新增可獨立導流的非市民頁面，合併 HCM＋BeClass 欄位、去除重複輸入、套用本節必填規則及一般退款帳戶用語；沿用 verified LIFF 身分及既有申請 owner |
| LIFF 送出結果 | registration receipt／readback | 顯示待工會核准與申請編號；只有正式核准後的 owner 結果才能顯示 A 開頭案件編號 |
| LINE 管理／LIFF 設定 | `ui_react/src/pages/line_management/LiffCardStudio.tsx`、LIFF configuration Query／Apply | 新增非市民頁面選項、導流目標及對應欄位／文案設定；runtime、頁面型別驗證、歷史及還原共用同一資料庫版本，不回退 JSON 或新增選單角色 |
| 客戶名冊／待核准需求 | `ClientRegistryPage.tsx`、`RegistrationApplications.tsx` | 可辨識非市民申請、查看完整合併資料與退款帳戶；核准完成回讀正式案件編號及建案結果，不能只建立客戶就顯示整案完成 |
| 客戶清單與詳細資料 | `ClientRosterPage.tsx`、`ClientRegistryDetailEditor.tsx`、虛擬帳號區 | 接受並呈現 A 開頭案件編號、非市民身分、完整資料及正式虛擬帳號；沿用現有各欄位 owner 編輯、查詢及名冊匯出 |
| 待辦看板與案件工作台 | `OrderWorkbenchV2Page.tsx`、`OrderWorkbenchV2Drawer.tsx`、`WorkbenchCaseStatistics.tsx` | 正常承接非市民案件及既有十三步流程；原統計排除非市民，另呈現年／季／月、期間數、年度累計與六種狀態的非市民獨立統計 |
| 媒合與推薦 | 候選查詢、月嫂意願、推薦確認既有畫面 | 接受新案件識別並讀取本案服務需求及非市民費率；候選規則、意願及確認流程不新增分支 |
| 契約與繳費資訊 | 現有契約產生／下載／送交／回收及繳費通知 | 套用非市民自費條文、本案費率、既有分期公式與正式帳號；保留簽署、LINE 提醒及文件不可變規則 |
| 服務日期、排班與履約 | 現有日期／排班、服務紀錄、異動、完工及兩端結算畫面 | 讓 A 開頭案件沿既有流程讀寫及返回同案，使用各 owner 的本案事實，不因新來源重建另一套流程 |
| 報表／案件統計 | `ReportsPage.tsx`、Reporting Query／XLSX | 既有案件受理總表、計數與對應匯出排除非市民；新增獨立非市民統計呈現，與看板採同一口徑 |
| 帳務中心與統計 | `FinancePage.tsx`、收款／付款工作區、案件帳務 | 新增「案件類別」：補助案件（預設）／非市民案件／全部案件；同步篩選案件明細、件數及金額合計，單案仍沿原 owner 金額及核銷結果 |
| 申請與核准 API／資料保存 | Case Import registration／approval、LINE identity typed boundary | 承接合併欄位、正式身分類別與可追溯核准建案時間；申請送出和正式建案分開；年度配號及正式資料建立需具既有冪等／競爭保護 |
| 共用案件識別與銀行解析 | Orders／Client Finance／Finance Import typed ports、API schema、查詢及匯出 adapters | 支援既有編號與新的 A 開頭編號，取消僅允許九位數的假設；銀行仍依正式虛擬帳號及對照解析，不能從案件外形猜帳號 |
| 資料結構與驗收 | 既有 owner schema、focused contracts／integration／UI tests | 後續盤點案件識別長度、索引、核准時間及年度流水保存能力；若需 schema，依 `10` 另走 fresh／preserve-data 執行門。本次不產生 migration 或測試檔 |

後續驗收至少涵蓋：非市民導流與獨立頁面、合併必填與退款欄位、送出不建案、核准才配號、跨年與並行核准／重播、帳號 `001 → 501` 正反解析、既有流程接續、自費契約／5 天定金及既有分期、案件統計互斥、帳務三選項與明細／件數／金額一致，以及補助案件既有流程不受新表單必填規則影響。此處只定義待驗收事項，未執行程式或 Browser 驗收。

### 5.2 State machine

2026-10-16 管理端匯入頁顯示裁決：HCM、Client BeClass、Staff Historical、Historical Orders
統一顯示「來源筆數／成功匯入／重複略過／未匯入」。完成結果三類互斥且合計等於來源筆數；
已成功採納但有欄位警示的列仍只計入成功匯入，review／警示 overlay 不額外增加筆數。
2026-10-20 人工補充裁決：四種匯入完成後均顯示本次「未匯入明細」，只取實際 terminal receipt
未匯入列，列出來源位置、可用的案件／查詢編號、問題欄位與去敏原因；HCM 使用資料序號，其他來源
使用 Excel 列號。成功但有警示的列與重複略過列不混入未匯入明細，也不額外增加筆數。
Client BeClass、Staff Historical、Historical Orders 的 additive `row_issues` 只保存實際未匯入列；
HCM 沿用既有 `row_outcomes`。新收據明細筆數須等於未匯入筆數；舊收據缺少逐筆資料時顯示
明細不可用，不以重新 Preview 猜測歷史結果，不改寫歷史收據。Staff 明細只用列號定位，不回傳身分證字號。
匯入頁仍移除成功列警示、問題導覽及頁內更正工作台；問題與更正由既有其他頁面承接，
不藉此改變 owner validation、待補件判定、writer 或歷史來源／收據。
Preview 尚無可靠執行結果時只顯示來源筆數，其餘以「—」呈現；完成後原位替換為唯一一組實際結果。
同一操作結果重查顯示原收據筆數並標明已處理，不將重查誤算為另一次成功寫入。
逾時／連線中斷維持結果待確認及既有同 key 查詢，不當成所有列未匯入。
錯誤訊息須區分瀏覽器等待逾時、連線中斷、閘道 502／504、服務不可用及匯入協調鎖等待，並顯示
穩定錯誤代碼。Client BeClass 的 coordinator lock timeout 表示等候同 key 處理鎖 30 秒未取得，
不代表檔案驗證失敗，也不能據此判定 NAS／網路故障。
只有匯入 Apply 的等待逾時、連線中斷、閘道 502／504 或處理鎖等待結果待確認時，UI 才每隔
5 秒沿用原始快照、Preview 與相同 idempotency key 自動確認，最多 6 次且同一時間只有一個請求。
確認期間維持換檔鎖；等待中與結果待確認時均提供「停止等待」，立即解除導覽鎖並停止後續自動確認。
停止等待不取消已送出的後端 Apply、不撤銷已寫入資料，也不宣稱成功或失敗；原請求未結束前不得再送查詢。
留在本頁仍可接收原請求結果，原請求結束後可沿用同快照、Preview 與 key 人工確認。離頁不受未儲存表單
的 busy 鎖阻擋；操作前須告知離頁後目前需重新選取原檔案確認結果，不宣稱自動恢復頁面。
成功、確定失敗或離頁即停止自動確認，達上限仍未確認則保留人工查詢及停止等待按鈕。
同日人工澄清：NAS 慢連線造成的鎖等待／回應逾時，在自動確認期間持續顯示「匯入處理中」
與中性等待說明，不顯示錯誤警示或要求使用者按查詢。四種 Apply 每次等待上限延長為 180 秒，
Client BeClass 協調鎖等待延長為 30 秒；不改 Preview 等待上限。自動確認次數用完仍未確認時，
以中性「等待時間較長，尚未取得最終結果」提示及人工查詢按鈕承接，不宣稱匯入失敗；確定失敗
才顯示錯誤警示。此調整不改 idempotency、writer、交易邊界或部署設定。
一般 503、驗證錯誤、衝突、回應契約錯誤不自動重送，也不加入通用 mutation retry。

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
- HCM Current 的案件身分唯一鍵是非空且合法的`查詢序號(案件編號)`。相同姓名、IP位址或兩者同時
  重複但案件編號不同，代表可合法重複申請／不同年度申請，必須建立新的Client／Order，不得自動綁定、
  合併或阻擋；可保存privacy-safe非阻擋警示供工會後續核對。只有案件編號已存在時才依same-source
  exact replay／conflict規則處理，且不得覆寫既有Client／Order。尚無唯一Client BeClass對方時，仍建立
  Client／Order並讓`requires_cooking = NULL`。
- 2026-10-13 人工裁決：HCM 工作簿新增 email 資料欄，原始表頭空白，位於「管理員註記」後一欄；
  既有「管理者註記事項」表頭亦為管理註記位置。adapter 只將此位置的原始空白表頭正規化為 `email`，
  不依 email 內容猜欄位、不把其他空白欄當成 email；位置歧義或與具名 email 欄衝突時拒絕匯入。
  此欄 optional，去除值的前後空白後匯入 Client-owned
  `clients.email`（nullable `VARCHAR(100)`）。缺欄／空白不形成缺件；非空但格式錯誤或超過 100 字
  形成 `hcm_field_invalid:email`，沿用 partial intake 將該主檔欄位存為 NULL，其餘合法欄位照常採納。
  主檔 email 與 BeClass original／effective email 各自保存，不互填、不覆寫；既有案件重匯仍維持
  exact replay／`skipped_existing`。2026-10-13 後續人工裁決：新版 HCM 對既有案件可僅補入空白的
  `clients.email`；已有非空值一律保留，來源空白不更新，非法非空值只回報 email 欄位問題。
  此列以案件編號定位既有案件，不以姓名、IP 或其他來源欄位重判建案身分；
  不採納姓名、電話、日期、服務條件等其他欄位，不做 BeClass reconciliation 或 bootstrap；
  BeClass original／effective email 維持獨立。Case Import 委派 Client Profile 的 email-only 補入命令，
  在工作簿唯一 outer UoW 內 fresh-lock／檢查空白值、沿用 profile version、事件與 receipt；任一失敗全批 rollback。
  Preview 顯示 `email_fill_count`，Apply／歷史結果顯示 `email_filled_count` 與 `email_filled` 逐列結果。
  Apply 前可補入筆數改變會使現有 workbook preview stale；鎖定後仍不覆寫非空值。
  已完成相同 workbook 的 idempotency／digest replay 優先回原 receipt，不能因補入後 eligibility 改變而錯報 stale。
  管理端人工補登仍走 Client Profile Preview／Apply。
- HCM Current 完整案件的訂金到期日固定為`min(報名時間日期 + 3 calendar days, 預計服務日期)`；
  急件不得只因報名距預計開工不足3天而阻擋Client／Order及case architecture bootstrap建立。
- HCM `服務方式` canonical值固定為`連續服務 | 休周六 | 休周日 | 週休2日`；legacy `週休1日`／
  `週休一日`正規化為`休周日`，`周休二日`／`週休二日`正規化為`週休2日`。`休周六`只排除星期六、
  `休周日`只排除星期日、`週休2日`排除星期六與星期日、`連續服務`不排除固定weekday；國定假日及
  人工覆寫仍依其正式規則處理。任何預計結束日、正式服務日、Scheduling、合約及天數／費用精算
  consumer都必須保留此weekday差異，不得再把`休周六`與`休周日`合併成`週休1日`。
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

2026-10-13 最新人工裁決：HCM 原始服務方式文字保留，不轉換別名、不因格式警示清空。
Case Import immutable source snapshot 保留文字；排班頁讀取原文供人員對照，人工休假星期
僅為當次日曆試算條件，確認後只保存服務日期，不新增保存欄位。原始欄位警示與正式日期確認保持各自既有 owner。

待辦看板的案件處理可直接修改 current HCM review 指出的 Client Profile 可編輯欄位，
沿用 Client Profile Preview／Apply 與既有驗證；2026-10-13 最新人工裁決：服務方式使用文字輸入，
保留非空原文、不轉換別名、不限制固定選項；去除前後空白後最多 100 字，符合既有欄位容量。
保存後重新讀取正式 Client 資料與 current HCM review，才更新缺件顯示。
日期、天數及其他 Orders 條件沿用 Orders writer。匯入驗證與轉換機制不變，
原始來源與匯入歷史不改寫。

2026-10-13 最新人工裁決：HCM `縣市` 僅為參考欄位，缺欄、空白或不在縣市清單中均不得產生
欄位警示、補件理由，或單獨使案件走 partial intake／待補件。沿用既有縣市與地址正規化，
不因縣市值未列於清單而清空主檔值；其他欄位驗證不變。current review Query 忽略歷史縣市
警示，包含尚無可讀正式 root 的紀錄；原始來源、歷史 review／receipt 與既有訂單狀態不改寫。

2026-10-13 後續人工裁決：HCM 欄位錯誤只有以下七項可觸發 partial intake／「待補件」：
`姓名`、`身分資格`、`報名時間(建檔)`、`預計服務日期`、`希望服務天數`、`服務時間`、`服務方式`。
其中 `服務方式` 依同日最新人工裁決僅缺欄／NULL／空字串／純空白才觸發待補件；非空文字
只作為後續排班的人員參考，不以允許值清單產生格式警示、觸發 partial intake 或要求補件。
匯入保留既有原文採納與前後空白處理，不轉換別名、不清空；current review 依最新非空規則
解除歷史服務方式格式警示，實際仍缺值者保留。既有日曆試算、人工休假星期與正式服務日期
確認沿用各自契約，不藉本裁決回寫既有待補件訂單或歷史來源／receipt。
其中身分資格決定費率／補助，報名時間決定訂金到期日，服務條件決定帳務與服務日計算。
其他欄位缺漏或格式錯誤僅形成欄位警示，不阻擋完整 Client／Order／case architecture bootstrap
建立；沿用既有逐欄 NULL 採納規則，合法欄位保留，服務方式原文依前述裁決保留。
電話（原始表頭仍為 `行動電話`）接受手機與含區碼的市話，沿用 Client-owned 電話正規化及格式規則；
電話缺漏／格式錯誤僅警示，不觸發待補件。縣市依前述裁決完全不警示。
Preview 與 Apply 均以可用案件編號為最低建案資格；報名時間錯誤可匯入為待補件，不能在 Preview
被當成不可匯入列。案件編號缺失或不可用仍不建案，既有案件仍沿用 exact replay／skipped_existing。
本裁決適用新匯入；不自動改寫既有待補件訂單狀態或歷史 receipt。

HCM partial intake 必須逐欄保存合法 Orders 條款：預計開始日、服務天數，以及已驗證服務時間
解析出的每日時數、開始時刻、結束時刻與跨日位移。不因姓名、身分資格、報名時間或服務方式
缺漏而將其他合法條款清空；只有來源對應欄位本身無效才留空。未齊全的案件仍不提前建立
帳務／薪資／排班 roots。補正其他欄位後，Orders 條款 Query 必須能回讀既有合法條款。

HCM 不得以 fabricated default 補造欄位。案件編號是最低寫入資格：有可用案件編號時必須建立／保留
正式案件，其他欄位缺漏、格式錯誤或身份關聯歧義各自形成 owner validation／review result；只有案件編號
缺失或不可用時不建案，且只保留來源 review／receipt／outbox 稽核，不投影異常中心。
Client／Staff historical import 必須另走 HistoricalAdoption
Preview／Apply，不得重用 current LIFF command 假裝一般資料更新。

### 匯入 owner review 的外部確認與重新提交

HCM、Client／Staff BeClass 與其他 Case Import 來源的 review 是公會人員聯絡來源當事人的待辦，
不是管理端直接修正資料的表單。review root、處理狀態與 disposition 必須保留去敏資訊；不得持久化
LINE 對話原文、完整聯絡資料或把回覆文字直接當成正式 Client／Order／Staff input。正確資料由
新來源重新走 typed Preview／Apply。2026-09-09 人工裁決補充：一般 HCM workbook intake 遇到相同案件
編號時不得以不同內容覆寫，也不得因此建立新的待處理異常；來源完全相同時回傳 exact replay，來源不同時
以 `skipped_existing` 終止該列並保持零業務寫入；唯一例外為上述既有案件空白 HCM email 補入。
2026-10-13 人工裁決退役 HCM 修正版工作簿入口、
`/api/v1/case-import/hcm/resubmissions/{preview|apply}` 與專用欄位修正命令；各頁面不再提供工作簿覆寫修正。
既有案件資料只經 Client Profile／Orders 等正式 owner 命令修改；不得修改 immutable source。

Issue #326 的欄位修正 Query 由 Case Import 提供 `/api/v1/case-import/hcm/reviews` 與
`/reviews/{review_identity}`：主清單只讀每案最新、已綁定案件的欄位 review，不使用已停用的 warning tracking。
2026-09-30 人工裁決：客戶名冊經既有 Client Profile／Orders terms 正式命令儲存後，
欄位警示由 Case Import Query 依最新 Client／Orders root values 重新驗證。Client Profile 可編輯欄位
沿用其正式欄位驗證與名冊允許值（不拿來源工作簿舊選項否定有效的住宅型態或生產方式）；其餘可判定
HCM 欄位沿用既有欄位規則。指定欄位已補齊且通過規則即自動解除，不要求另有 HCM resubmission correction event；只儲存其他欄位、
資料仍缺漏／格式不符、未支援欄位或無法確認正式 root binding 時，警示仍保留。
同筆 review 有多個欄位時逐一檢查，只顯示仍未解決的欄位；全部解決才退出主清單。
Query 維持零寫入，不刪除或改寫原始來源、review、receipt 或稽核歷史，也不新增跨 owner commit。
既有更正事件的 after fingerprint 仍綁定 resulting review version，供歷史事件處理與稽核使用；
不可用前端刪列或 immutable workbook receipt 判定問題已解除。伺服器先套目前問題 predicate 再分頁；一般 workbook preview 的「來源欄位檢查通過」
不承諾新增或更新，Apply 的 skipped_existing 仍為零覆寫。來源／身份／bootstrap 問題保留各自 owner 的入口。

2026-09-30 人工裁決：資料中心移除獨立的「目前 HCM 欄位待修正資料」區塊及其讀取、分頁控制。
客戶資料由客戶名冊修改，儲存後沿用上述 Query 規則自動解除欄位警示；既有 review Query API 保留。
本次工作簿的問題明細仍留在匯入收據內，收據只供本次結果與歷史追溯，不作目前問題主清單。
2026-10-13 人工裁決移除匯入頁「在本頁提交修正」及修正區塊，保留結果與問題明細，不替換成異常審核入口。
畫面使用白話原因，不顯示 internal issue code；身份疑義與 bootstrap／費率或案件初始設定問題
仍依既有 owner 分流，不得誤導為一般 workbook 覆寫。

#### 2026-10-01 人工裁決：異常欄位的實際處理入口

Authority：本次人工要求預產期問題直接開啟客戶名冊、缺少不符合原因可補填或略過；並明確確認
略過須保留人工紀錄、只解除該項警示、不改案件「不符合」狀態，也不填入虛構原因。

- `HCM-REPAIR-01`：異常頁以既有 canonical current review Query 呈現每案所有仍未解決欄位及分頁；
  不再以 legacy warning tracking 作 HCM 欄位警示的主清單。姓名、電話、預產期等 Client 欄位直接
  開啟 `#clients?case=...&field=...` 對應案件的名冊資料；Orders 條件仍使用既有 Orders writer。
  2026-10-13 人工裁決退役原工作簿修正次要入口及 API。服務方式直接開啟 Client Profile 的 `service_type`；
  無正式編輯入口的欄位只保留問題與人工略過，不新增通用 writer。current review 的 `can_correct` 固定為 false，
  `unavailable_reason` 為 `hcm_workbook_correction_retired`，不影響既有 owner 欄位編輯能力。
- `HCM-REPAIR-02`：Client Profile 管理端允許修改既有 `clients.due_month` 與 `clients.reject_reason`。
  日期以有效 `YYYY-MM-DD` 保存，不符合原因為非空文字、最長 500 字。沿用 profile version、
  Preview／Apply、audit event 與 receipt；不增加資料欄位、不修改 Orders 狀態機，也不擴張 LIFF
  applicant 的可修改或可查閱欄位。補填後由原 current Query 逐欄解除。
- `HCM-REPAIR-03`：Case Import 提供 `/hcm/reviews/{review_identity}/skip-missing-reject-reason/{preview|apply}`。
  只接受目前已綁定案件的 canonical review 所含 `hcm_field_missing:不符合原因`，且目前原因仍為空。
  Preview 零寫入；人工明確確認後 Apply fresh-lock、重查 current review 與版本；stale 為 typed 409。
  不接受其他欄位或格式錯誤的通用略過。
- disposition 沿用既有 `case_import_hcm_correction_events`／receipt／outbox，
  `adopted_field_paths=["review.skip_missing_reject_reason"]` 明確表示 review disposition，並非 Client
  欄位採納。保存 canonical review identity、actor、固定處理原因、review version 與 idempotency；
  Client／Order 零寫入，root before／after fingerprint 相同。Query 只針對同一 canonical review 的
  這項 disposition 解除原因警示，其他缺漏仍保留；新 review 不沿用舊略過。
  客戶名冊的案件變更歷程顯示該筆人工略過的原因、操作人與時間，供人員回查。
- 驗收：名冊深連結選中案件與欄位；有效日期及原因沿用正式 writer；多欄位逐一顯示；略過須確認且
  刷新後仍解除該項；Apply 失敗不得假移除；已補原因、舊 review、version conflict 為零寫入；
  same-key/same-command 回原 receipt，same-key/different-command 衝突。

#### 2026-10-01 後續人工裁決：所有目前警示可逐筆略過

Authority：使用者要求歷史取消訂單直接解除警示，確認只提供每筆略過，並明確包含匯入資料
及 LINE 通知失敗等其他目前異常。此裁決 supersede 上述只允許缺少不符合原因略過的限制，
以及 §5.4「異常頁不提供人工 closed」對匯入警示的限制；不授權批次清除或自動略過。

- 所有已綁定 current HCM review 的缺漏／格式欄位均可透過
  `/hcm/reviews/{review_identity}/skip-field/{preview|apply}` 逐欄略過。
  `source_field` 必須是該 review 目前仍顯示的欄位；有效補齊、已略過、舊 review 或版本變更拒絕。
  使用既有 correction event／receipt／outbox，marker 為 `review.skip_field:<source_field>`；
  舊缺少原因 API 與 marker 保留。Query 只移除同一 review 已保存的略過欄位，新 review 不繼承。
- 其他匯入警示（含客戶連結疑義、未綁定來源及歷史訂單）沿用既有 tracking Preview／Apply
  的人工 `closed`，reason_code=`manual_warning_skip`，只解除該 occurrence 的提醒。
  同案不同 occurrence 不合併成一個待辦；每筆均可單獨處理。
- `LINE-006` 由 LINE owner 提供 `/line/notification-rules/failures/{issue_key}/skip/{preview|apply}`。
  Preview 對 exact case/reason fresh readback；Apply 驗證 owner snapshot、同 scope lock、idempotency，
  在既有 LINE UoW 保存 `line.notification.warning_skip` audit（操作人、時間、固定人工略過原因）
  與 command receipt。audit 的 aggregate identity 綁定 exact owner snapshot token，不創造送達成功、
  不取消任務、不重送通知；同一 snapshot 不再需要人工提醒，來源或結果變更後仍可建立新警示。
  fresh owner readback 完整且 predicate false 後，在同 UoW 移除 current projection，並追加既有 bounded recheck。
- 全部操作均由使用者逐筆確認，Client／Orders／immutable source／Delivery 結果不被改寫，
  不增加 schema，不操作 production 或 provider。解除失敗不得由前端假移除；刷新後保持解除，
  保存人工歷程並保留原處理入口。HCM 欄位略過顯示在客戶名冊變更歷程；其餘沿用各 owner audit。

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

#### Case pairing current anomaly decision matrix（2026-08-31）

`BECLASS-001`與`IMPORT-003`共用 Case Import 既有 source intake／Preview／Apply／accepted-mapping
contract，不建立平行 linking framework。owner readback 以 exact lane source identities、current review／mapping
versions 與 case identity 形成 snapshot token，並回報 `authoritative_complete`。新來源 Apply 或 mapping
reconciliation 在既有 outer UoW 內一併寫入 bounded `anomaly.recheck` intent。

| Code／subject | Active predicate（current roots） | 唯一合法 owner operation | Completion predicate | Closed unresolved reasons |
|---|---|---|---|---|
| `BECLASS-001` / `case_no` | HCM case source 已存在，但沒有唯一、一致的 Client BeClass counterpart accepted mapping | 正確 counterpart 以 `IngestCaseImportSource` 進入後，沿用 `Preview／ApplyCaseImport`驗證與採納；歧義或衝突只能保留 owner review，不得在 Anomalies 選候選或模糊比對 | exact HCM 與 Client BeClass sources 形成唯一、一致、可追溯 accepted mapping，owner fresh readback 完整 | `counterpart_missing`, `counterpart_ambiguous`, `mapping_conflict`, `owner_readback_incomplete` |
| `IMPORT-003` / `entity_kind + review_item_id` | Client BeClass source 已存在，但沒有唯一、一致的 HCM counterpart accepted mapping | 正確 counterpart 以 `IngestCaseImportSource` 進入後，沿用 `Preview／ApplyCaseImport`驗證與採納；人工聯絡、tracking closed 或姓名／電話相似都不是 completion | exact Client BeClass 與 HCM sources 形成唯一、一致、可追溯 accepted mapping，owner fresh readback 完整 | `counterpart_missing`, `counterpart_ambiguous`, `mapping_conflict`, `owner_readback_incomplete` |

```yaml
convergence:
  status: READY
  requirement_ids: [CASE-ANM-BECLASS-001, CASE-ANM-IMPORT-003, CASE-ANM-PAIRING-READBACK]
  acceptance_ids: [CASE-ANM-ACTIVE, CASE-ANM-OWNER-QPA, CASE-ANM-TERMINAL, CASE-ANM-FAIL-CLOSED]
  blockers: []
```

上述`READY`代表behavioral contract已收斂。若原identity-conflict review由different-source identity的
後續accepted source解除，Case Import Apply必須在同一owner UoW保存exact immutable
`original_review_identity → accepted_source_event_identity → accepted_result_identity` lineage；不得以review
resolved、tracking state、姓名、電話、case status、source filename或identity字串轉換推測。2026-08-31
repository-local successor已依此契約完成，synthetic counterpart、same-source accepted receipt與different-source
accepted lineage均由同一owner readback驗證；runtime DB engine仍須依current release gate另行驗收。

#### HCM review 與既有修正證據（2026-10-13 人工退役裁決）

- HCM 修正版工作簿的 Preview／Apply、`ClientHcmCorrectionCommand` 及專用 Client／Orders adapters 已退役。
  一般 intake 的 exact replay／`skipped_existing` 契約維持；Client Profile 與 Orders 正式 writer 不受影響。
- `服務方式` 仍是 Client root fact，canonical persistence 為 `clients.service_type`；Orders 不新增
  `service_type`。`end_date` 仍由 Orders terms／lifecycle 衍生，Client Profile 不直接重算它。
- canonical review identity／version、欄位 root 映射與既有更正事件讀回保留，供 current Query、
  逐欄人工略過及 committed outbox 處理。legacy association 只作 provenance，不再轉介退役命令。
- `case_import_hcm_correction_*`、Client correction version／event／receipt、既有 schema release、
  migration、原始來源與稽核歷史均保留。人工略過仍沿用同一 outer UoW、typed stale conflict、receipt／outbox；
  不以停止工作簿修正為由刪表、改寫事件或停止處理已提交事件。
- 此退役只授權 local code／test／規格同步；不包含 production DB、migration Apply、deployment 或 provider 實送。

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

Scheduling Matching Coordination 是 Scheduling subsystem；`accepted` 只進 fresh-effects check，產生 typed Assignment conversion/rematch request，LINE／Orders／Assignment／Payroll root writer 不被接管。M3 Phase D 只可透過 typed ports 整合 leave／assignment owner。管理員個人通知 target enable／disable 共用既有 advisory serialization boundary、opaque CAS 與 same-key replay；群組告警登錄與重設已取消；lock failure 固定 0 write，commit 後 release unknown 不回 success 並以原 key 查 receipt。Customer Service 擁有 HIGH escalation；Anomaly 只作 source，escalation 不競寫 `runtime_alert_application`。

M3 的 service-date Apply 必須在單一 outer UoW 內 fresh-lock owner service dates、assignment與shifted-date availability後重算preview。leave Preview／Apply只讀Scheduling-owned immutable canonical receipt；Apply須在同一outer UoW重新讀取並把receipt identity、version與fingerprint綁入完整M3 source tuple。package／criteria／leave version／original staff／preview任一stale時，必須在M3 lineage、receipt與intent前rollback；M3不得藉此寫Leave、Orders、Assignment、Payroll或直接呼叫LINE provider。

本 amendment 的 initial freeze 不單獨授權 mutation；後續人工裁決已核准 M1-A、M2-A、M3-A～D、M4-A
的 exact production implementation slice。LINE／AI provider、deployment、production DB、未另行核准的
schema／DDL與 external side effect 仍不在授權範圍。

## 2026-10-22 群組告警退役

依最新人工裁決，群組告警已取消，不是暫停或待啟用；舊同群重綁要求不再有效。
`設定異常通知群組` 不登錄、不回覆成功、不建立投遞；群組重設／啟用 API 與群組專用審核連結簽發／使用拒絕操作。
管理端不得提供群組登錄教學、分類推播或虛構訊息模擬；預覽收件人不得寫死為幹部群。
既存群組告警工作在 provider 前拒絕，不改寫歷史投遞、receipt、audit 或已發布 schema。
保留管理員個人告警與歷史 Query／撤銷，以及案件服務群組的綁定、成員紀錄與私人邀請。
