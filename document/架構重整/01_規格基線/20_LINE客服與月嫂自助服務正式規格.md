# LINE 客服與月嫂自助服務正式規格

## 1. 範圍、主切邊界與基本不變量

本文件定義 LINE 客服工單流程、Webhook 同步回覆（`line_webhook_reply`）、月嫂端 LIFF 自助服務、管理端 LINE 工作台／手機審核，以及 `LINE-PAY-01`～`08` 繳款提醒與收據通知的現行正式契約。

- **Domain 邊界**：LINE Integration 與 Customer Service 只擁有平台身分關聯、Webhook 收件、投遞任務、客服工單與對話事件；訂單、排班、客戶帳務與月嫂應付等根事實仍由各自 owning Domain／Subsystem 唯一擁有並經既有 canonical writer 提交，UI 與 LIFF 不得旁路寫入業務根事實。
- **授權與主切**：所有非公開 LIFF 頁與自助服務 API 皆以 `server-verified LINE token` 結合伺服器端 `line_identity_bindings` 作為唯一授權依據；query string 上的 `userId`、顯示參數或未驗證前端狀態僅作導航輔助，不得構成授權或身分依據。舊入口退場後維持唯一新線，僅保留明確設定 `LINE_LEGACY_ROLLBACK_MODE=true` 時之緊急回退開關；禁止隱性雙寫與靜默回退。
- **PII 與憑證邊界**：送往群組訊息、公版預覽或通用審計的摘要一律套用去敏或明確欄位投影，禁止外洩未遮罩手機號、身分證字號、完整地址或原始 provider payload。

## 2. 客服工單生命週期與 M4 重大升級（Customer Service）

### 2.1 一般觸發與工單狀態機

客服工單主鍵由 Customer Service canonical writer 維護，狀態固定為 `waiting` → `handling` → `resolved`。

1. **觸發分離**：一般文字提問、`問題`、`其他問題`、`詢問`、`5`、`6` 與身分核對失敗等輸入一律導向自助服務導覽或提示修正，不得自動建立客服工單；停用中的 AI 回應錯誤／繼續／恢復等回頭按鈕只回覆停用提示，不開單亦不解除既有客服狀態。只有明確點擊「聯絡專人服務／專人協助／聯絡工會人員」或符合正式客訴入口時，才進入客服受理。
2. **計畫 A 獨立建單與接續規則**：
   - 當使用者目前最新一筆工單為 `waiting` 或 `handling` 時，新進留言直接追加至該進行中工單並維持其處理狀態。
   - **已結案永不重開**：當使用者所有歷史工單皆為 `resolved` 時，再次觸發「聯絡專人服務」一律新建全新 `ticket_id` 與獨立 `created_at_utc`，進入 `waiting` 並回覆固定受理文案「已通知客服人員為您處理，請稍候。」；禁止將先前已結案工單改回 `waiting` 或 `handling`。
3. **共用待辦池與結案通知**：
   - 工單採工會共用待辦池，不依單人認領狀態過濾清單。
   - **React 管理端結案**：管理員於 React `#line-management` 客服分頁按下「處理完成」將工單轉為 `resolved` 時，僅更新系統狀態，**不向客戶 LINE 發送結案推播**。
   - **其他合法結案路徑**：非 React 管理端客服結案路徑完成時，發送固定結案訊息「您的客服案件已處理完成。如仍有問題，請再次呼叫專員。」；任何路徑於 `resolved` 後再收到「聯絡專人服務」皆依計畫 A 新建工單。
4. **冪等與並行鎖定**：重複觸發同一進行中工單之受理請求須冪等回傳同工單識別；接手、回覆與結案皆以 versioned optimistic concurrency 與 inbox/outbox 交易隔離保護（常見 typed errors：`customer_service_ticket_not_found`、`customer_service_ticket_version_conflict`、`customer_service_transition_invalid`）。

### 2.2 M4 重大客訴與高優先升級

正式客訴或 Anomaly 產生之 `HIGH` 等級異常經 M4 escalation ingress 進入 Customer Service：
- 同交易建立或升級 `HIGH` 優先級工單與 `waiting`／`hold` 狀態，並於 outer UoW 提交後透過 outbox 觸發已設定之管理員個人告警（不發群組告警，詳見 [`17A_LINE_Gateway_Inbox與通知投遞正式規格.md`](17A_LINE_Gateway_Inbox與通知投遞正式規格.md)）。
- 支援 `create`、`claim`、`handling`、`resolve` 與解除 `hold` 流程；每次轉態回傳具 version 與 receipt 的 typed result，並於解除時驗證無殘留阻塞狀態。

## 3. Webhook Reply-Only 與 Push 投遞分工（`line_webhook_reply`）

LINE 官方帳號回應依是否具備有效一次性 `replyToken` 嚴格區分同步回覆與主動推播：

### 3.1 `line_webhook_reply` 涵蓋範圍

下列兩類互動固定走純 `line_webhook_reply` 同步回覆通路，**禁止 fallback 改走 Push API**：

1. **第一批 — 一般文字、綁定引導與選單回覆（15 類靜態回覆）**：歡迎詞／操作引導、未綁定提示、客戶／月嫂身分綁定回覆、群組設定指令格式錯誤與未註冊提示、人工客服受理／進行中追問回覆、已停用 AI 按鈕提醒、以及預設未知文字引導文案。
2. **第二批 — 五項 Postback 互動按鈕即時確認（Batch 2）**：
   - 媒合階段月嫂意願按鈕 ack（願意／詢問回應）；
   - 媒合推薦客戶端 Postback 按鈕 ack（接受配對／專人協助／已回應）；
   - 服務開始當天當日排班月嫂 Postback ack（正常服務／需要協助）；
   - 請假或交接代班月嫂 Postback ack（願意代班／無法代班）；
   - 訂金催繳或繳費疑問「專人協助」Postback ack。

### 3.2 `line_webhook_reply` 執行與驗證契約

- **時窗與嘗試上限**：單次 `line_webhook_reply` 任務最大嘗試次數固定為 `1`，有效時窗為自 Webhook `received_at` 起 **45 秒**。逾時、缺少有效 `replyToken` 或 LINE API 失敗時，立即標記為不可重試終態失敗（`non-retryable`），完整寫入投遞紀錄供稽核，**絕不降級改發 Push 訊息**。
- **同室同事件檢核**：任務投遞前須比對關聯之 `line_webhook_events` 記錄，確認 `line_event_id` 存在且回覆對象與原來源聊天室／群組完全一致。
- **Fast-Path 優先排程**：Inbox Worker 單批抽取時，保留最多 `min(floor(batch_size / 2), 25)` 的同步快速通道名額優先消化 `line_webhook_reply` 以壓低回覆延遲，同時保留至少半數名額予一般事件與 Push 隊列，避免飢餓。

### 3.3 `line_push_worker` 保留範圍

主動通知、定時提醒、LIFF 送出後跨請求確認、卡片主體與多氣泡組合仍維持 durable outbox → `line_push_worker`：含 Flex 媒合／推薦／請假／完工卡片、開工當天群組詢問卡本體（`LINE-ORDER-SERVICE-START-DAY-CARD-V1`）、`order.service_start_day` 群組訊息、`second_payment_due` / `second_payment_settled`（第二期入帳沿現行 rule ID `LINE-SECOND-PAYMENT-SETTLED-TEXT-V1` 維護）、簽約與訂金催繳、繳款收據、人工客服回覆與取消／退款／追償通知。

## 4. 月嫂端 LINE 自助服務

月嫂通過姓名、身分證字號與生日綁定唯一 `staff_id` 後，透過 `staff_menu` 開啟高對比、大字版自助服務頁面。

### 4.1 個人案件查詢與班表檢視

- **案件查詢（`staff_order_search.html`）**：呼叫 `GET /api/v1/line/staff-self-service/orders`，呈現個人承接中、待開工、已完成案件及曾受徵詢但尚未指派之案件（支援從詳情重新表達接案意願）。
- **個人班表與服務開始日（`staff_schedule.html`）**：只讀顯示 Scheduling `effective` 逐日排班，不納入歷史 buffer。正式開工日當天之服務狀況詢問依 [`02_Assignments_Scheduling_Domain.md`](02_Assignments_Scheduling_Domain.md) `SSTART-01`～`08` 處理：無衝突且雙方約定時由本人經 LIFF 提交新服務日並同交易更新排班與第一期款到期日；拒絕或衝突時轉交工會代班流程，代班人須點選群組邀請加入後由工會登記日期（`handover-v1`）。

### 4.2 請假與調休協調（`leave-v1`）

- 月嫂於一對一聊天室開啟「班表與請假」，選定案件與受影響服務日並填寫雙方群組已協議之新日期：
  - **無衝突順延**：Scheduling fresh-lock 檢核無檔期衝突即同交易更新正式服務日、排班與連動帳務，並向原案件服務群組發送無確認按鈕之最新日期表，不須工會額外核准或詢問客戶確認。
  - **需代班或存在衝突**：自動建立工會內部待辦；工會另行徵詢代班人選（Postback ack 走 `line_webhook_reply`），確定願意且實際加入原服務群組後由工會補記新日期與群組日期表。
- 歷史雙邊確認 API `/api/v1/line/staff-self-service/leave-requests/{id}/confirm` 永久回傳 `410 Gone`。

### 4.3 寶寶日誌、餐食照片與缺漏催繳退役規則

- **日誌與照片機制**：`staff_baby_log.html`、`/api/v1/line/staff-self-service/service-day-logs` 及 `/api/v1/line/staff-self-service/service-day-media` **一律永久回傳 `410 Gone`**。寶寶日誌與餐食照片維持由月嫂直接於各案件 LINE 服務群組相簿上傳新增，系統端不建立表單、不接收圖檔上傳、不驗證相簿數量，亦不作為排班、完工、請款或付款之前置門檻。
- **缺漏催繳退役**：基於系統日誌計算之連續缺漏（原 3 天計算與每日催繳推播／待辦清單）已全面退役，不得於資料庫無日誌時發出誤報催繳；日常督導改由工會於服務群組相簿人工查閱。

### 4.4 正常完工滿意度通知（`LINE-SERVICE-COMPLETION-TEXT-V1`）

當訂單經 canonical `Orders` 流程轉為 `訂單完成` 時，於原案件 LINE 服務群組發送一次固定結案致意文案與問卷連結欄位；若 `survey_url` 尚未設定則留白輸出（不填範例假網址）。投遞失敗不回滾 `Orders` 完工狀態。

### 4.5 月嫂薪資明細查詢與訂單異動通知

- **薪資查詢（`staff_payout.html`）**：唯讀呼叫 `/api/v1/line/staff-self-service/payouts`，呈現已結算或待出款明細。
- **訂單異動通知**：`ORDER_CANCELLED`、`CLIENT_REFUND_NOTICE` 與 `CLIENT_BACK_COLLECTION_NOTICE` 依正式事件非同步派送私人／群組通知；當對象未綁定 LINE 或缺乏有效投遞通道時，不靜默失敗，一律產出工會內部人工通知待辦與去敏告警摘要。

## 5. 管理端 LINE 工作台、手機審核與 LIFF 設定

### 5.1 管理端桌面分頁與客服六欄清單

LINE 管理介面依 [`19_Global_Entry_Point_Governance.md`](19_Global_Entry_Point_Governance.md) 拆分為四個獨立桌面入口，另整合 `#notifications` 全域通知中心：
- **`#line-management`（客服與營運）**：整合即時客服清單（`tickets`）、身分綁定查詢／撤銷與審核（`binding`）以及服務群組作業（`order_groups`）。
  - **React 客服六欄表規格**：呼叫 `GET /api/v1/customer-service/tickets/reminders`（單批個人資料補水上限 100 筆、最高 4 並行請求、總預算 2 秒），固定只渲染六欄摘要欄位；不設額外狀態分頁籤、右側明細抽屜、行內回覆框或刪除按鈕。
- **`#line-notifications`（通知與寄送）**：整合統一通知與發送工作台（`push_queue`，支援 `?tab=push_queue&message=<id>` 定位）與寄送追蹤／異常，並維護含 Flex 在內之通知文案／設計公版；M4 重大升級與繳款收據深連結（`#notifications?subtab=payment_receipt`）於通知事項頁跟催。
- **`#line-interface`（LINE 介面設定）** 與 **`#line-ai-events`（AI 客服工作室）**：
  - `#line-interface` 包含圖文選單（`visitor`／`customer`／`staff`／`union_staff` 四角色草稿）、**LINE 表單工作室（`LiffCardStudio`）** 與 LINE 流程圖；表單工作室固定涵蓋 17 個官方 LIFF 表單與行動工作面預覽項目（含 `gateway.html` 兩步導流、`register.html` 需求調查、`non_citizen_registration` 非市民服務申請與四個 `mobile_admin` 視圖，不含 `staff_baby_log.html` 與 Flex 訊息卡片），並提供 `NonCitizenLiffSettingsPanel` 非市民設定面板。
  - `#line-ai-events` 維護 AI/FAQ 知識庫、引導動作、回答測試、回饋分析與模型設定。

### 5.2 手機審核中心、DB 版控 LIFF 設定與非市民入口契約

- **`line-mobile-admin`**：統一行動審核入口，包含 `staff_review`、`customer_service`、`order_tracking` 與 `dashboard` 四個視圖。原獨立群組／主管異常推播已退役，管理員改從 `line-mobile-admin?target=staff_review` 頂端可收合系統狀態摘要卡（`retired_admin_alert` 狀態）查閱告警總覽。
- **LIFF 設定唯一來源與 DB 版本控管**：
  - 服務申請入口（`gateway.html`）、需求調查（`register.html`）、帳號綁定（`bind.html`）、非市民申請頁（`/line-non-citizen-registration`）及管理端設定統一讀寫 MySQL 之版本化 `LIFF` 設定（`LineConfigurationKind.LIFF`）。[`config/liff_settings.json`](../../../config/liff_settings.json) 僅於資料庫尚未建立 LIFF 設定（`revision = 0`）時供明確 fresh bootstrap，執行中禁止 fallback 讀檔；設定缺失、格式錯誤或資料庫不可用回 `503`，頁面不存在或停用回 `404`。
  - 公開與管理端沿用既有 `/api/config/liff`、`/api/config/liff/runtime`、`/api/config/liff/state`、主題／頁面／欄位設定（`/api/config/liff/theme`、`/api/config/liff/pages/{page_id}` 與欄位新增／修改／刪除）、版本歷史（`GET /api/config/liff/history`）與還原（`POST /api/config/liff/rollback/{revision}`），並共用 `LiffSettingsConfig` typed validation。`ETag`／`If-Match` 採資料庫 revision 執行樂觀併發檢查，讀取後遭並行更新回 `409`；還原於目前 revision 新增一版且不覆寫或刪除既有版本，所有設定異動僅留存版本與稽核，不建立訊息投遞或選單發布工作。
- **入口分流與非市民 LIFF 頁面設定（`NonCitizenLiffSettingsPanel`）**：
  - `/line-gateway` 的正式畫面與後台預覽依 [服務閘道 §2](29_LINE服務說明、客服互動與選單角色正式規格.md#2-服務閘道gateway登記入口與歡迎詞規則) 呈現兩步分流。市民已登記與非市民已建案共用 `/line-bind`，各自依 §2 處理核對不到或資料不完整的結果。既有直接連結仍到原目的地。一般需求問卷使用 `/line-registration`。非市民專用合併表單固定由 `/line-non-citizen-registration`（後端於 `<body>` 注入 `data-registration-kind="non_citizen"`）開啟。
  - 非市民設定由 `GET /api/config/liff/non-citizen`、`POST /api/config/liff/non-citizen`（明確初始化建立）與 `PUT /api/config/liff/non-citizen` 維護，共用上述版本化 `LIFF` 設定與 `If-Match` 衝突控制。既有站台須透過同一設定服務保存新版導流，保留與新版相容的自訂文案、其他設定及歷史版本。新站台的初始設定應包含完整兩步導流。既有版本仍可讀取與還原，重複套用同一導流設定不得新增重複選項。
  - 保留既有輔助導流與 `register` 補助問卷設定，非市民必填系統欄位受共用 schema 驗證保護不得停用或設為選填（違規回 `422`／`409`），且非市民必填規則不套用到其他申請類別。送出僅存入專用 Redis 待審申請並依實際回執顯示申請編號與「待工會核准」（不宣稱已建案或完成綁定），正式建案與 `A` 字頭編號規則見 [`17B_Case_Import與非市民Redis待審正式規格.md`](17B_Case_Import與非市民Redis待審正式規格.md#3-非市民自費進件與專用-redis-7-待審隔離架構)；新增頁面不新增 Rich Menu audience、選單發布或外部 provider 授權。

### 5.3 資料異動審核（`profile_update` / `order_update`）

- **`profile_update`**：管理客戶基本聯絡資料與退費相關資訊之申請；服務縣市（`city`）、詳細地址（`address`）與居住類型（`residence_type`）統一移至 **`order_update`** 處理，且 `order_update` 採純 URI 導向、依訂單鎖定狀態限制欄位修改。
- 送出異動後產生紅綠 Diff 待審工單，須經工會人員於桌面端或 `mobile_admin` 明確核准後才透過 Client／Orders canonical writer 更新主資料；尚未建立正式排班與帳務鎖定前之 `OrderTerms` 更新可先反映至 `OrderTerms`，已鎖定訂單依既有變更管制阻擋。

## 6. Flex 條件協調、`feedback` 與繳款通知契約（`LINE-PAY-01`～`08`）

### 6.1 `flex_dispatch` 與人工條件協調

- 保留 8 種結構化條件協調模板供工會撰寫詢問與發送確認卡；月嫂「沒有意願」只儲存回覆並標示無意願，不自動改單或對客戶重組文案；候選池為空提示與客服閒置定時自動推播已全面退役並回傳 `410 Gone`。
- **滿意度回饋（Feedback）**：對單筆回應記錄 `resolved | unresolved` 評價與 audit metadata；標為 `unresolved` 時同交易連動建立或提示 Customer Service 客服工單。

### 6.2 `LINE-PAY-01`～`08` 繳款提醒與人工收據規範

| 代碼 | 對象與觸發時點 | 通路與文案邊界 | 停止／安全機制 |
|---|---|---|---|
| `LINE-PAY-01` | 訂金逾期提醒（人工作業觸發） | 一對一私人 LINE 訊息，顯示案號、金額與專屬／指定帳號；含「專人協助」Postback（走 `line_webhook_reply`） | 不可主動寄群組；不從聊天室截圖自動核銷 |
| `LINE-PAY-02` | 第一期款逾期提醒（開工日後未繳） | 一對一私人 LINE 訊息 + `#payment-reminder-settings` 可編版型 | 正式入帳核銷前重複查詢不重複建單 |
| `LINE-PAY-03` | 第二期款逾期提醒（對比應收與到期日） | 一對一私人 LINE 訊息（第二期正常開工當天通知另有群組專屬模板） | 無第二期或已結清者嚴格排除 |
| `LINE-PAY-04` | 自動二次追蹤機制 | 首次逾期提醒發出滿 24 小時仍未入帳時，最多自動補發 **1 次** | 客戶在私人聊天室發送任何回覆或已完成核銷時立即終止追蹤 |
| `LINE-PAY-05`～`07` | `#payment-reminder-settings` 排程與模板管理 | 由 `GET /api/v1/line/payment-overdue-reminders/schedule` 與 `PUT /api/v1/line/payment-overdue-reminders/schedule` 維護 Asia/Taipei 排程，並提供訂金／一期／二期（含 `LINE-SECOND-PAYMENT-SETTLED-TEXT-V1`）共 10 種帳務 LINE 模板管理與唯讀預覽 | CAS expected revision 防覆蓋，佔位符由後端 typed resolver 注入，拒絕未定義變數 |
| `LINE-PAY-08` | **人工發送繳款收據**（訂金／一期／二期） | `GET /api/v1/line/payment-overdue-reminders/receipts` 查詢候選，`POST /api/v1/line/payment-overdue-reminders/receipts/send` 人工按鍵發送私人收據 | **嚴格人工觸發**，銀行對帳單核銷後不自動代發；按鈕旁及 `#notifications?subtab=payment_receipt` 提供直達財務對帳頁面 `WF-02` 之深連結 |

> 未綁定 LINE 之客戶於各期催繳與人工收據清單皆明確顯示「尚未綁定（需人工聯繫）」；所有提醒與收據皆遵守重複核銷／重試冪等鍵，不得因工作器重跑導致客戶重複收訊。
