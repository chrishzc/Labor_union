# LINE 客服與月嫂自助服務正式規格

## 1. 文件狀態

- 狀態：`approved-first-release-baseline`
- 人工確認日期：2026-08-11
- 上位契約：`17_External_Integration_LINE_Access正式規格.md`
- 視覺來源：`merge` 分支 Rich Menu、客服及 LIFF 面板
- 執行架構：`wen` canonical LINE inbox、identity、delivery 與 Rich Menu publication
- 2026-08-21 M2/M4 amendment：production full AI rejected；Phase 1 deterministic harness＋durable manual
  fallback frozen，Customer Service owns HIGH escalation／automation hold；implementation、schema／DB、provider
  與外部副作用仍未授權。
- 2026-08-23 current implementation amendment：M2-A deterministic／manual fallback與M4-A escalation backend
  已獲人工核准並落地；LINE／AI provider、deployment與未另行核准的schema／DB仍不在此授權範圍。

## 2. Global 不變量

1. LINE webhook 只保存 canonical inbox event；業務處理由 consumer 執行。
2. 所有 LINE 回覆皆建立 durable delivery task，不在 webhook 或管理 UI 直接呼叫 LINE。
3. LIFF 正式身分只信任 server-side 驗證後的 ID token 與正式 binding；query string userId 不是身分證明。
4. LINE Integration 不擁有 Orders、Scheduling、Customer Service 或客戶主檔狀態。
5. Rich Menu 圖面與文字可沿用 merge，但 definition、revision、publication 與 per-user binding 仍以 wen DB 為 SSOT。
6. `綁定訂單`、`訂單查詢` 固定進入 customer binding；`綁定後台帳號` 固定進入 admin binding。
   Service Help／Customer Service 不得攔截或重定義這三個既有 identity aliases。
7. `工會選單`、`開啟客服系統`、`月嫂驗證管理` 只接受已 bound 的 admin LINE identity，並透過
   Rich Menu binding outbox 套用 `union_staff_menu`；`esc` 對所有 LINE user 透過同一 outbox
   套用 `default_menu`。兩者都不直接查 legacy role table、直接寫 task 或呼叫 LINE API。
8. 2026-08-12 人工授權 canonical cutover：webhook 與 worker 的未設定預設都是 `canonical`。
   `legacy` 僅可由 webhook／worker 同時明確設為 `legacy`，且 production 必須另設
   `LINE_LEGACY_ROLLBACK_MODE=true` 才能作受控 rollback。

## 3. Customer Service Domain

### 3.1 責任與 SSOT

Customer Service 擁有客服需求、對話事件、處理狀態、處理人與版本。LINE user、client、case 只保存可追溯 reference；正式客戶與訂單資料仍由其原 Domain 擁有。

根事實：ticket ID、LINE user ID、category、client/case reference、原始訊息、status、version、actor、created/updated/resolved time。衍生值包含狀態標籤、今日統計與遮罩顯示值。

### 3.2 狀態機

```text
waiting → handling → resolved
             ↑          │
             └──────────┘ 新訊息重新開啟
```

不允許跳過狀態驗證或以 UI 字串決定 transition。管理 command 必須帶 expected version；stale command 回 conflict。

### 3.3 交易、冪等與 retry

- inbound event：ticket create/append、狀態事件、ack delivery task 同一 LINE Unit of Work commit。
- canonical webhook dispatch 任一業務處理失敗時，該 business Unit of Work 必須整筆 rollback；rollback完成後
  才可另開新的 Unit of Work，只保存`retryable_failed`／`terminal_failed` inbox completion。禁止把部分ticket、
  binding、outbox或其他業務 mutation與failure completion一起commit。
- admin reply：鎖定 ticket、驗證 version、保存回覆、更新狀態、audit、delivery task 同交易 commit。
- inbound idempotency 使用 LINE event ID；admin mutation 使用 caller idempotency key。
- provider timeout/5xx 只 retry delivery task；validation、authorization、stale conflict 不自動 retry。
- retry exhausted 建立 LINE runtime alert，客服資料不得因 provider 暫時失敗回滾。

### 3.4 Typed errors

- `customer_service_ticket_not_found`
- `customer_service_ticket_version_conflict`
- `customer_service_transition_invalid`
- `customer_service_category_invalid`
- `customer_service_delivery_unavailable`

## 4. Service Help Subsystem

精確 intent 為「服務說明」及六分類別名。分派順序固定為 identity、group、service help、knowledge fallback，避免「綁定」或知識問答搶走 intent。

第一版行為：

1. 服務說明：回覆六分類選單。
2. 服務流程、收費與補助：回覆核准文案。
3. 查詢服務進度：只查已綁定客戶最新案件；未綁定則送 canonical 綁定入口。
4. 修改登記資料、聯絡工會人員、其他問題：建立或延續客服需求。
5. 同一 LINE user、同一 category 同時最多一筆未完成 ticket；exact replay 不追加重複訊息。

## 5. Staff Self-Service Subsystem

### 5.1 訂單查詢

以 verified LINE identity 對映 staff subject，再由有效 `case_staff_assignments` 限制可見案件。姓名或案件編號只作該授權集合內篩選，不可擴大權限。

### 5.2 排班查詢

重用 `subsystems.scheduling.staff_monthly_calendar_query`，以 assignment-owned `staff_schedule` 與正式 availability lock 投影。不得新增另一套排班 SQL writer。

### 5.3 請假

LIFF 不得直接改正式排班。已驗證、已綁定月嫂可提交起訖日與去敏說明，僅建立
Scheduling-owned 的 `pending` 請假待辦、immutable event 與 idempotency receipt；不得輸入案件、
正式服務日、代班人或帳務資料。管理人員的受理、拒絕、取消只處理該待辦，受理一律顯示為
「已受理處理」，不是正式核准。

管理人員須以一次性 request context 前往既有案件行事曆，重新執行 Leave/Substitution
Preview／Apply；其版本、fingerprint、mutex 與跨 Domain impact 不得省略。只有 canonical Apply
receipt 已提交、且確定原月嫂與 request 相同並尚未被其他 request 關聯時，request 才能標為
`resolved`，再排入 canonical LINE delivery task 通知月嫂。delivery 失敗不回滾已提交的排班或
request 結案；timeout／5xx 只由既有 worker 重試。

請假審核 API、管理 client 與 UI caller 屬 Scheduling；不得附加到 LINE identity review route
或 `LineAdminApiClient`。LINE Integration 只接受已提交的通知 intent 並回報 delivery outcome。

月嫂 LIFF 的提交 transport 固定為 Scheduling-owned 的
`POST /api/v1/line/staff-self-service/leave-requests/preview` → 使用者確認 →
`POST /api/v1/line/staff-self-service/leave-requests/apply` →
staff-scoped typed readback。Preview 必須零寫入，僅接受起訖日與去敏說明，並重新驗證 LIFF token
與正式 staff binding；Apply 必須以同一 intent、opaque preview fingerprint 與 idempotency key
重新驗證後才可建立 `pending` 待辦。fingerprint、binding/version 與 LINE user identity 只供契約驗證，
一般 LIFF 畫面不得顯示。readback 必須再次驗證同一綁定月嫂，只回傳申請期間、去敏說明、
業務狀態與必要申請編號；不得讓月嫂讀取他人的申請。既有直接提交 endpoint 不得成為新 UI caller，
也不得作為略過 Preview／確認的正式路徑。

Scheduling Matching Coordination 可唯讀引用已提交的 canonical Leave/Substitution receipt 作為 rematch
source fact；Preview不得寫入，Apply須在自己的單一outer UoW內fresh-read該immutable receipt並驗證case、
leave version與original staff。M3只保存receipt reference與自己的lineage，不得改寫請假、排班或代班根事實。

Typed errors：

- `liff_token_invalid`
- `line_staff_binding_not_found`
- `staff_order_not_visible`
- `staff_schedule_query_invalid`
- `leave_request_preview_stale`
- `leave_request_not_found`

### 5.4 寶寶日誌與餐食照片

Rich Menu 的「寶寶日誌」開啟月嫂 LIFF。LIFF 只可用 server-side 驗證的 ID token 與已綁定月嫂身分；
後端依正式指派與服務日驗證後，才允許月嫂提交自己服務日的日誌。Scheduling 是日誌、附件關聯、
完成 event、receipt 與 outbox 的唯一 owner；LINE Integration 只提供身分入口、受控檔案傳輸與已提交
通知投遞。

每一服務案／指派／服務日最多一筆有效完成日誌。Orders root 的 `requires_cooking=true` 時，日誌完成
必須附至少一張餐食照片；`false` 時不要求；未知、關聯不唯一、檔案未保存或驗證失敗時一律不建立完成
事實。照片以受控 object reference 與去敏 metadata 保存，禁止放進 LINE 訊息 payload、URL query 或
日誌文字欄。日誌完成只停止後續提醒，不直接改正式排班、訂單或付款狀態。

照片 bytes 依 `00` §2.2 保存於工會地端受控 NAS；MySQL 只保存 Scheduling-owned 附件關聯、opaque
object reference、digest、MIME、size、版本與狀態。LIFF／管理端只顯示檔案清單投影，不暴露 NAS 路徑、
storage locator 或公開 URL；查看使用 authenticated download，重新處理後以受控上傳或指定投放區形成
新版本，不提供 Web 資料夾瀏覽或原地修改。月嫂即時新增照片仍須經 verified identity、assignment／
service-day 驗證、staging、Preview／確認／Apply；不能因 NAS watcher 發現檔案就建立日誌完成事實或發送通知。

## 6. UI 與人工入口

- merge 的 Rich Menu 圖面、按鈕標籤與 LIFF 卡片樣式可移植。
- 「客服與選單」的 Rich Menu 編輯器必須提供背景圖與按鈕顯示名稱的 draft 編輯入口；畫面預覽、
  Preview receipt 與 Apply 必須鎖定同一 revision。編輯草稿不等於發布，provider publication 仍依 `17`
  的 durable saga 執行；未啟用 provider 測試時只驗證到 committed definition／publication intent，不假造發送成功。
- 手機模擬器點擊每個熱區時，必須使用同一 draft revision 的真實 typed action；管理員可依 `17` §3.5
  修改 action kind 與該 kind 的 allowlisted target／內容。按鈕顯示名稱修改不得改變 action，action 修改也
  不得靠標籤推導；Preview、Apply 與 readback 必須讓編輯器、手機模擬及 server definition 顯示同一結果。
- Rich Menu 本機預覽不是待移除的 demo：它是正式編輯 UX 的零寫入互動層。編輯背景、標籤、action 或
  message text 後，手機畫面立即更新；點擊 message 只在模擬器顯示候選文字，點擊 URI／LIFF 只顯示該
  typed target 的模擬頁，不送訊息、不開 provider mutation。另保留獨立 server Preview、確認與 Apply。
- React 管理端固定保留「客服與選單」、「AI 事件工作室」、「LIFF 卡片工作室」、「群組與安全」四個獨立入口；
  API adoption 不得以未接線為由刪除既有設計功能、控制項或業務說明。
- LIFF 卡片工作室保留 8 個 LIFF 與 4 個 Flex 原始資產。已有 canonical route 的項目可產生不含 identity／token
  的真實測試連結；缺 route／typed owner 的項目保留設計並明示 contract gap，不得以 demo token、樣本個資、
  假 provider payload 或不存在的 URL 補空。真實測試連結的 origin 由既有 LIFF runtime-config 回傳經驗證的
  `LINE_PUBLIC_BASE_URL`／`BASE_URL`；不得由 React 硬編 localhost、夾帶帳密、query、fragment 或身分資訊。
- LIFF 卡片工作室中央手機模擬器必須維持可閱讀的正常手機比例與最小內容寬度，不得被左右工作區 flex/grid
  壓縮成狹長欄；窄螢幕改為堆疊或可捲動配置。移除黃色區域中「原始 8 個 LIFF 與 4 個 Flex 功能均保留」等
  實作／盤點說明，該資訊只留在正式規格，不作為一般操作者畫面內容；移除說明不得刪除、隱藏或停用任何
  8 個 LIFF、4 個 Flex 資產與其既有操作入口。
- legacy `/static/bind.html` 只可保留為導向 `/line-identity` 的相容入口；query string 可原樣帶往 canonical
  頁面作導航，但不得參與身分或授權判斷。`profile_update.html` 在正式異動契約完成前只保留唯讀設計與
  人工補登指引，不得呼叫不存在的 API、接受 client-supplied `line_user_id` 或呈現假成功。

LIFF 資產入口對齊狀態（2026-08-25）：`completed`。工作室保留 8 個 LIFF 與 4 個 Flex；
`gateway.html`、`bind.html`、`identity.html` 明確共用 `/line-identity` canonical shell，其餘已存在入口由
runtime `public_base_url` 產生公開網址。Chrome 已由工作室逐一實點並核對正式頁面；
`profile_update.html` 仍明確顯示待建且不導向假頁面，其正式 Query／Preview／Apply 工作仍由 §6.1 列管，
不因本項入口對齊完成而視為完成。Staff verified-token 與 provider delivery 亦不包含在本項完成範圍。
手機模擬器在桌面與窄視窗均維持 360px 正常寬度，窄容器改為工作區內局部水平捲動；8 個 LIFF、
4 個 Flex 仍可達，且一般畫面不再顯示資產盤點說明。本項 responsive UI 驗收亦為 `completed`。
- AI 事件工作室在正式 catalog contract 完成前，只允許零寫入草稿編輯與 deterministic 本機預覽；未命中固定
  轉人工 fallback。滿意度調查按鈕與統計槽位不可因 API 尚缺而刪除；正式 feedback Query／record／receipt 完成前
  只顯示本機預覽，不保存回饋、不增加硬編統計、不假造人工工單。正式規則 Query／Preview／Apply／receipt、
  客戶 `profile_update` Query／Preview／Apply／receipt與去敏 Flex design preview 目前均為 required contract gap；
  不得誤用 notification schedule、legacy client-supplied `line_user_id` writer 或 delivery raw payload 取代。
- 客戶「已填過／尚未填過」選擇必須保存 canonical flow ID；未填過流程完成登記後才能完成同一 LINE 身分綁定。
- LINE 管理中心使用 Customer Service bounded API client；成功 payload 轉 typed Pydantic view，transport/schema error 轉 typed client error。
- Streamlit 只顯示 typed result 與提交 command，不包含 ticket transition 或 SQL 規則。
- 已綁定且 enabled 的工會人員可由 `line-mobile-admin` LIFF 查看／回覆客服案件與決定月嫂身分審核；其 server-side ID token、binding、version、receipt 與 outbox 規則不因 persisted role／capability 而改變。

### 6.1 LIFF 資料異動申請與管理核准（2026-08-25 人工裁決）

`profile_update` 不再是唯讀設計槽位；正式目標是 verified LIFF 使用者提出資料異動申請，經工會
管理人員審核後，由資料 owner 的 typed command 更新 DB，最後讓 LIFF 與管理端讀回一致結果。

1. LIFF 只接受 server 驗證的 ID token 與 current binding；query-string `userId` 只能保留導航資訊，
   不得決定申請人、subject、權限或 DB target。
2. 申請 payload 必須是 owner 核准的欄位 allowlist、目前 owner version、requested values、去敏原因與
   idempotency identity。LINE Integration 只擁有 intake／binding evidence，不得直接更新 Client／Staff root。
3. 提交採 `PreviewProfileChangeRequest` → 使用者明確確認 → `ApplyProfileChangeRequest` → applicant-scoped
   receipt/readback；Preview 零寫入，Apply 只建立 immutable pending request，不代表資料已修改。
4. 管理端必須顯示 current value 與 requested value 的人可讀差異、subject、request version、必要 evidence
   與明確業務 blocker；一般 UI 不顯示 fingerprint、raw token、binding id、SQL、storage locator 或完整敏感值。
5. 核准採 owner-specific `PreviewApproveProfileChange` → 管理員明確確認 → `ApplyApproveProfileChange`。
   Apply 在單一 outer UoW fresh-lock request、binding、subject 與 owner version，由 owning repository 更新
   canonical DB root、append approval event／receipt／outbox 並 commit；route、LIFF、LINE callback 與 UI
   不得直接 SQL。拒絕只更新 request workflow，不修改 owner root。
6. Apply 成功後必須重新 Query owner DB projection與 request outcome；管理端和 applicant-scoped LIFF readback
   都要顯示相同的新業務值與 `approved_applied`。receipt 已提交但 readback 失敗時，顯示 outcome unknown 並
   只允許 reconcile，不得盲目重送或宣稱未修改。
7. stale owner version、已終結 request、same-key different payload、未綁定、subject mismatch、欄位未允許、
   validation failure 或 transaction failure 固定 fail closed；same-key same-payload replay 回原 receipt。
8. Browser 驗收必須實際由 LIFF 提交、管理端核准並讀回 DB 更新；另驗證拒絕、stale、replay、越權、
   rollback 與合法唯讀原因。不得以 API mutation、直接 DB patch、假 token 或改狀態欄取代 UI。

若 owner root、欄位 allowlist、version 或 repository contract 尚未存在，實作狀態為 `blocked`，須先由
Client／Staff 正式規格補齊；本裁決不自行授權 schema／migration／DDL、production DB 或 provider push。

## 7. 第一版驗收

1. 服務說明回覆六分類且 exact replay 不重複建立 task。
2. 客服需求可建立、列表、查看、更新、回覆及完成。
3. 客服回覆透過 canonical delivery worker 發送。
4. 偽造 URL userId 無法讀取客戶、月嫂訂單或班表。
5. 月嫂只能讀取自己的有效 assignment 案件與班表。
6. merge Rich Menu 圖面／文案可由 wen publication 流程發布並 fan-out。
7. 客戶前導頁保留 flow ID，兩條路徑都不退回 legacy gateway。

## 2026-08-21 M2／M4 routing and escalation amendment

- explicit human／wrong 優先於所有自動路由。含 `human`／`wrong` marker 的 inbound 不得進 identity alias、AI、Knowledge 或 Service Help 自動回答；只有不含 marker 且 exact match protected identity alias 才可進 identity。
- production full AI 現在不核准；Phase 1 僅允許 deterministic harness、source-cited typed outcome 與 durable manual fallback，Phase 2 維持 proposed。active automation hold 時連 deterministic auto-reply 也禁止。
- Customer Service 是 HIGH escalation／ticket／hold／人工處理的 owner；Anomaly 僅提供 source projection。escalation 透過 typed `TicketReferral`／escalation port，不競寫 M2 `service_help` 或 M4 `runtime_alert_application`；Scheduling 不在 escalation transaction。
- production composition必須注入automation hold／escalation gateway；active hold會在任何deterministic reply、ticket或
  delivery intent前fail closed。human escalation採`create → claim → handling → resolve`，每步驗證version、
  idempotency與typed receipt，resolve後才解除hold。
- `reply_provider` direct path已由durable delivery task取代；Service Help只enqueue，不在webhook transaction呼叫
  provider。LINE provider仍只能由已提交task的worker執行；本規格不授權AI provider、deployment或新的外部副作用。
- runtime／LINE管理畫面的audit清單只能使用closed masked typed view；raw details、token、完整identity或額外欄位
  一律在API client boundary fail closed，不得穿透Streamlit／React render。
