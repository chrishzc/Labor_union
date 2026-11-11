# LINE Gateway、Inbox 與通知投遞正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：LINE Integration Domain（`domains/line/`、`subsystems/line/`）
- 單一負責範圍：LINE Webhook Inbox、Durable Delivery Task（租約 worker 與 M4 Safe Review Link）、好友事件時間保序、`LINE-006` 失敗 readback／人工補送／逐筆略過、群組告警與管理員個人告警退役契約（`/runtime/query`）、服務群組綁定／全體與代班單人邀請（`order-group-todos`）、服務開始／完工／二期／開工當天原群組通知、Rich Menu 草稿編輯與發布 saga、通知文案全面維護／公版預覽／表格圖片（`LINE-PREVIEW`、`LINE-COPY`、`LINE-TABLE-IMAGE`），以及私人日誌照片傳輸代理（`NAS-LINE-04`）。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Anomalies Domain](06_Anomalies_Domain.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[LINE 身分管理與解除](23_LINE身分管理與解除正式規格.md)、[LINE 服務說明與選單角色](29_LINE服務說明、客服互動與選單角色正式規格.md)、[Controlled File Storage NAS](30_Controlled_File_Storage_NAS正式規格.md)。

## 2. LINE Webhook Inbox 與 Delivery Task 骨架

- **LINE Ownership 邊界**：擁有平台 `user_id / group_id`、friend state（`unknown → active ↔ blocked`）、inbound webhook evidence、outbound delivery task／attempt ledger、`line_identity_bindings`／review、Rich Menu definition 與 controlled media 關聯；不擁有業務單據狀態或金額。
- **Webhook Inbox（`received → processing → completed | retry_pending | failed | ignored`）**：同 HTTP 批內事件共保存於單一 ingestion 交易，個別 event 獨立處理與交易隔離；缺 `webhookEventId` 以版本指紋識別。dispatch 任一步業務失敗整筆業務 UoW 回滾，再另開交易記 `retryable_failed`／`terminal_failed`。`follow / unfollow` 為官方帳號好友事件：僅維護目前好友狀態（時間早於 `last_event_at` 之晚到事件僅留歷史而不倒退目前好友狀態），系統不於 `follow` 建立身分流程或發送歡迎訊息（加入好友歡迎訊息改由 LINE 官方帳號設定）。
- **M2 路由優先序**：全面採用確定性規則與持久人工轉介（禁止無拘束 AI 自動決策）；明確人工／誤判標記優先於自動比對；Service Help 僅寫入 committed delivery task 而不在 webhook 交易直呼 provider。
- **Delivery Task（`pending → processing → sent | retry_pending | failed | cancelled`）**：
  - Worker 每輪逐筆取得短效未過期租約（預設批大小 25 筆）並於送前重驗未取消；同鍵入列必回既有 task／receipt。
  - **業務通知投影規則**：
    - `order.service_start_day`（開工當天原群組通知）：見 [LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md) §3.3／§4.1；包含未清第一期款提醒與服務狀況按鈕；`order.pre_start_reminder` 已完全停用取消。
    - `client.second_payment_due`／`client.second_payment_settled`（二期群組純文字通知）：見 [LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md) §6.2；送前重讀需求、金額、日期與群組；缺群組入 `LINE-006`；舊前三日私訊已停用。
    - 服務完工群組通知：僅消費帶 `line_service_completion_notification=true` 的新完工 outbox，發送一次文字通知（問卷連結先保留空欄或既有網址配置）。
    - 服務開始與換人結果日期表：僅發送至本案群組（無「確認／拒絕日期表」按鈕），投遞失敗不回滾正式排班。
- **安全觀察端點（Zero Commit／Zero Wakeup）**：
  - `GET /api/v1/line/configurations/{kind}/safe`（僅回傳 `kind`、`revision` 與 `state=empty | configured`，禁洩漏定義、URI 或任何 secret）。
  - Delivery public masked query（限 allowlist 篩選與真實總數分頁，禁止以 `user_id`／payload／raw error 過濾或回傳）。
  - `GET /api/v1/line/identity/reviews/numbered`（真實 DB `COUNT + LIMIT/OFFSET` 分頁；待審隊列無自動逾期或時間升級，僅限具認證人員依 [身分管理規格](23_LINE身分管理與解除正式規格.md) 手動審核，legacy internal-key-only 審查端點回 `410 Gone`）。

## 3. 服務群組綁定、待辦與代班邀請

- **觀察與待辦（`GET /api/v1/line/order-groups/numbered`、`GET /api/v1/line/order-groups/{case_no}/events/numbered`、`GET /api/v1/line/order-groups/workspace/numbered`、`GET /api/v1/line/order-groups/workspace/{case_no}`、`GET /api/v1/line/order-groups/workspace/{case_no}/events/numbered`）**：依真實分頁顯示加入／離開事件與狀態；「尚未建群」待辦端點 `POST /api/v1/line/mobile-admin/order-group-todos` 僅列正常未結案、正式訂金 `settlement_state='settled'` 且金額 `> 0` 尚無服務群組之案號；提供一鍵複製 `綁定訂單 {case_no} 〈本群組邀請網址〉` 格式而不暴露真實 `group_id` 或邀請網址於管理 Query。
- **群組指令**：
  - `綁定訂單 {case_no} {邀請網址}`：具 `ORDER_GROUP_BIND` 且已綁定 LINE 之工會人員輸入（接受單／多空白、全形空白或換行；僅接無額外參數 `https://line.me/ti/g/...` 或 `https://line.me/R/ti/g/...`；儲存至私有 `line_order_group_bindings.invitation_url`）。
  - `發送邀請`：於群組重新檢查資格後為媽媽與所有已綁定指派月嫂排入私人邀請卡片（按鈕開啟群組連結）；發送前群組／網址／訂金／人員變動即自動取消舊工作。
- **代班／換人單人邀請（`SSTART-05` / `handover-v1`）**：依 Scheduling 授權對單一已選定且願意承接之月嫂發送原群組連結（不重複邀請全體）；分開回讀「已排入／已送達／失敗／真正入群」。

## 4. `LINE-006` 失敗管理、Safe Review Link 與告警退役

- **群組告警與管理員個人 Push 全面退役（`NAS-LINE-03`）**：`設定異常通知群組` 及管理員個人告警 Push（含 `runtime_health_event`、`customer_service_escalation`、`runtime.alert.review_required`、`complaint.ingress.hold_high_ticket`）已正式退役，舊 target 寫入回 `410 Gone`、未寄工作於 provider 前取消。管理員主動於 LIFF 待辦工作台頂端透過唯讀摘要端點 `/api/v1/line/mobile-admin/notification-task-actions/runtime/query`（驗權後回整體／worker 狀態與計數，禁曝錯誤詳情或對象）檢視運行現況（無主動推送案件狀態標 `unknown`）。
- **M4 Safe Review Link**：`IssueSafeReviewLink`／`Redeem`／`Revoke`／`Query` 使用 `issued → redeemed | expired | revoked` 一次性憑證（DB 存 digest＋immutable `runtime_alert_target` 證據，LINE payload 禁夾帶原始 token／URL）。
- **`LINE-006`（`case_no + notification_reason`）**：`LINE Notification` 計算每個適用失敗來源是否皆具備有效 terminal `manual-replay:{source_event_id}:{idempotency_key}` 後繼成功（未取消案件之未送達來源不因設定錯誤失效）；工會可逐筆人工確認略過（`POST /api/v1/line/notification-rules/failures/{issue_key}/skip/{preview|apply}` 寫入綁定 exact owner snapshot token 之 `line.notification.warning_skip` audit 後清除 current issue；來源變更後可重現）。

## 5. Rich Menu、通知文案編輯與表格圖片

- **Rich Menu 草稿與發布 saga**：`QueryRichMenuDraft`／`PreviewRichMenuDraftChange`／`ApplyRichMenuDraftChange` 依 `(menu_definition_id, configuration_revision)` 區分 `editable | processing | published`（published 快照只讀可由此建立下一草稿）；管理台可改背景圖（含 `image_asset_id`／`sha256`／`image_asset_version` 檢查）、按鈕名稱與動作（`uri | message | postback | richmenuswitch` 互斥清空舊欄位），並以 NAS 唯讀預覽結合記憶體即時手機模擬。發布 saga 由 `line_rich_menu_publication_step_acknowledgements`、`attempt_events` 與 `cleanup_anomalies` 保存斷點與冪等重試，發布成功後依角色 fan-out 綁定既有合法身分（不阻擋身分審核原子提交）。
- **Notification Rules Admin**：規則管理以 `configuration → intent → task` 順序加鎖；禁用未知 event 或 `{} -> {"rules":[]}` 漂移；儲存／停用同交易取消相應排程任務。
- **通知文案編輯器與公版預覽（`LINE-PREVIEW-01～08`、`LINE-COPY-01～05`、`LINE-COPY-EDITOR-01～02`、`LINE-COPY-CATALOG-01`）**：
  - 由 `GET /api/v1/line/message-previews/catalog`、`GET /api/v1/line/message-previews/subjects` 與 `POST /api/v1/line/message-previews/preview` 提供公版索引、對象搜尋與即時渲染；目錄依 `MESSAGE_TEMPLATES` 維護全部通知文字與確認卡片（編輯框統一寬度 `504px`、每頁 `6` 則、正式媒合僅列「正式媒合－客戶完整推薦確認包」，保留各身分獨立成功文案 `identity_bound_customer | _staff | _admin` 與 `PUT` CAS 版本防衝突）。
  - 「通知與發送」工作台使用零寫入公版 `data_source=sample`（`Cache-Control: no-store`，固定範例不含真實個資或發送動作），僅工會詢問／回覆卡開放純瀏覽器記憶體草稿預覽。
- **三張表格圖片渲染（`LINE-COPY-TABLE-01`、`LINE-TABLE-IMAGE-01～04`）**：
  - 初步候選聯絡與正式推薦皆產生「訂單資訊一、資訊二、每週服務安排」三張表格 PNG（月嫂版資訊一僅含薪資單價／預估總薪資／預計付款日；客戶版僅含客戶費用與繳款約定；確認按鈕留存獨立互動卡）。
  - 圖片快照凍結於 outer UoW 投遞資料；端點 `GET /api/v1/line/table-images/{token}` 以 7 日不依賴外部排班金鑰的內部短效 opaque token 動態產出 PNG（`private, no-store, nosniff, no-referrer`），缺少系統中文字型或金鑰異常回 `503` 而不退回純文字。

## 6. 私人日誌照片媒體傳輸（`NAS-LINE-04`）

- NAS 環境對外日誌照片上傳與下載經專用隔離代理路由 `/internal/v1/line-media/`（由 `line-media-proxy` 憑證驗證原 LINE ID token、目前綁定與本人當日服務權限），公開 DB 帳號對受控附件與日誌主檔嚴格限制唯讀 `SELECT`。
- 本人附件下載 `POST /api/v1/line/staff-self-service/service-day-logs/{log_id}/photos/{file_id}/download` 驗證該日誌附件歸屬後回傳私密 `JPEG/PNG` blob（`no-store/nosniff`，禁止 URL query 傳 token）。

## 7. 驗收標準

1. 驗證 Inbox 斷點回滾重試與 `follow/unfollow` 保序、Worker 租約防止重播、群組 `綁定訂單／發送邀請` 與單人代班邀請各階段狀態分離。
2. 驗證 `NAS-LINE-03` 退役端點 410 與 `/runtime/query` 去敏摘要、`LINE-006` 逐來源重播及 skip 解除、Rich Menu 三態草稿與 3-table saga、文案 `504px` 公版預覽、`table-images` 受眾薪資／費用分離，及 `NAS-LINE-04` 跨憑證下載防護。
