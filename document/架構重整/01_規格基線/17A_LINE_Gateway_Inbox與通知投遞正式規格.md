# LINE Gateway、Inbox 與通知投遞正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：LINE Integration Domain（`domains/line/`、`subsystems/line/`）
- 單一負責範圍：LINE Webhook Inbox、Durable Delivery Task（租約 worker 與 M4 Safe Review Link）、好友事件時間保序、`LINE-006` 失敗 readback／人工補送／逐筆略過、群組告警與管理員個人告警退役契約（`/runtime/query`）、服務群組綁定／全體與代班單人邀請（`order-group-todos`）、開工當天群組問候、服務開始與換人結果日期表群組通知、Rich Menu 草稿編輯與發布 saga、通知文案全面維護／公版預覽／表格圖片（`LINE-PREVIEW`、`LINE-COPY`、`LINE-TABLE-IMAGE`），以及私人日誌照片傳輸代理（`NAS-LINE-04`）。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Anomalies Domain](06_Anomalies_Domain.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[LINE 身分管理與解除](23_LINE身分管理與解除正式規格.md)、[LINE 服務說明與選單角色](29_LINE服務說明、客服互動與選單角色正式規格.md)、[Controlled File Storage NAS](30_Controlled_File_Storage_NAS正式規格.md)。

## 2. LINE Webhook Inbox 與 Delivery Task 骨架

- **LINE Ownership 邊界**：擁有平台 `user_id / group_id`、friend state（`unknown → active ↔ blocked`）、inbound webhook evidence、outbound delivery task／attempt ledger、`line_identity_role_bindings`／role binding events／review、Rich Menu definition 與 controlled media 關聯；不擁有業務單據狀態或金額。
- **Webhook Inbox（`received → processing → completed | retry_pending | failed | ignored`）**：同 HTTP 批內事件共保存於單一 ingestion 交易，個別 event 獨立處理與交易隔離；缺 `webhookEventId` 以版本指紋識別。dispatch 任一步業務失敗整筆業務 UoW 回滾，再另開交易記 `retryable_failed`／`terminal_failed`。`follow / unfollow` 為官方帳號好友事件：僅維護目前好友狀態（時間早於 `last_event_at` 之晚到事件僅留歷史而不倒退目前好友狀態），系統不於 `follow` 建立身分流程或發送歡迎訊息（加入好友歡迎訊息改由 LINE 官方帳號設定）。
- **M2 路由優先序**：採用確定性規則處理明確自助指令。一般詢問、客服及客訴由工會在 LINE 官方帳號直接處理。Webhook 完成驗簽及收件後，提交即時 Reply 所需的業務寫入與投遞紀錄，再呼叫 LINE Reply。其餘業務交背景處理，背景不補發 Reply 或以 Push 替代。詳見 [LINE Reply 規格](20_LINE客服與月嫂自助服務正式規格.md#32-line_webhook_reply-執行與驗證契約)。
- **同事件即時與背景處理**。同一事件兼有即時 Reply 與背景業務時，保留 Inbox 租約至 Reply 嘗試結束後交回背景。程序中斷時沿既有租約逾期回收，詳見 [LINE Reply 規格](20_LINE客服與月嫂自助服務正式規格.md#32-line_webhook_reply-執行與驗證契約)。
- **Delivery Task（`pending → processing → sent | retry_pending | failed | cancelled`）**：
  - Worker 每輪逐筆取得短效未過期租約（預設批大小 25 筆）並於送前重驗未取消；同鍵入列必回既有 task／receipt。
  - **業務通知投影規則**：
    - 契約簽署與 LINE 通知分工見 [簽約規格 §3.3](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#33-檔期衝突檢核送交記錄與官方帳號提醒)。
    - **`order.service_start_day`（開工當天群組問候）**：依 Scheduling 確認的正式開工日，在台北時間開工當天依現有開工日通知時段，向本案已綁定的服務群組排入每案一則純文字 Push。依 [LINE-PAY-02](20_LINE客服與月嫂自助服務正式規格.md#62-繳款提醒與人工收據規範)，第一期款有未結清餘額時，才將繳款提醒追加到同一則文字。無第一期款或已結清時仍發送問候。第一期款排程與通用通知規則不得另外排入開工問候或同日第一期首次提醒。重跑排程及重試沿用同一通知識別。送出前重驗正式開工日、群組綁定及第一期款狀態，避免已結清仍催繳。缺有效群組時留供工會查核，不改投私聊；過去開工日不因啟用此通知而補發。`order.pre_start_reminder` 維持停用。
    - `client.second_payment_due`／`client.second_payment_settled`（二期群組通知）：停止投影群組通知，殘留群組工作於投遞前取消。繳款提醒及入帳通知見 [LINE-PAY-03 與 LINE-PAY-08](20_LINE客服與月嫂自助服務正式規格.md#62-繳款提醒與人工收據規範)。
    - `order.service_completed`（完工事件自動投遞）：系統不消費 `line_service_completion_notification` 標記或 Push。規則儲存拒絕，殘留工作於投遞前取消。月嫂從群組小幫手取得問卷的流程依[滿意度調查問卷規格](20_LINE客服與月嫂自助服務正式規格.md#44-滿意度調查問卷)。
    - 服務開始與換人結果日期表：僅發送至本案群組（無「確認／拒絕日期表」按鈕），投遞失敗不回滾正式排班。
    - 案件群組月嫂專屬小幫手選單（含【確認開工日】、【服務排程】、【雙方合意延期】、案件群組留言指引與【客戶常見疑問標準回答】）：月嫂輸入喚醒詞「工會」或「小幫手」及後續各步驟操作（確認單產出、雙方同意、排程查詢、舊協助按鈕的留言指引與標準回答）固定走 `line_webhook_reply` 同步回覆，全程 0 Push 額度消耗。
- **安全觀察端點（Zero Commit／Zero Wakeup）**：
  - `GET /api/v1/line/configurations/{kind}/safe`（僅回傳 `kind`、`revision` 與 `state=empty | configured`，禁洩漏定義、URI 或任何 secret）。
  - Delivery public masked query（限 allowlist 篩選與真實總數分頁，禁止以 `user_id`／payload／raw error 過濾或回傳）。
  - `GET /api/v1/line/identity/reviews/numbered`（真實 DB `COUNT + LIMIT/OFFSET` 分頁；待審隊列無自動逾期或時間升級，僅限具認證人員依 [身分管理規格](23_LINE身分管理與解除正式規格.md) 手動審核，legacy internal-key-only 審查端點回 `410 Gone`）。

## 3. 服務群組綁定、待辦與代班邀請

- **觀察與待辦（`GET /api/v1/line/order-groups/numbered`、`GET /api/v1/line/order-groups/{case_no}/events/numbered`、`GET /api/v1/line/order-groups/workspace/numbered`、`GET /api/v1/line/order-groups/workspace/{case_no}`、`GET /api/v1/line/order-groups/workspace/{case_no}/events/numbered`）**：依真實分頁顯示加入／離開事件與狀態；「尚未建群」待辦端點 `POST /api/v1/line/mobile-admin/order-group-todos` 預設僅列正常未結案、正式訂金 `settlement_state='settled'` 且金額 `> 0` 尚無服務群組之案號；提供一鍵複製 `綁定訂單 {case_no} 〈本群組邀請網址〉` 格式而不暴露真實 `group_id` 或邀請網址於管理 Query。
- **開工問候未送出紀錄**。工會 LINE 工作台「通知事項 → 訂金已付尚未建群 → 開工問候未送出紀錄」沿用同一端點的 `view=opening_greeting_skips`，依時間由新至舊分頁顯示因未綁定有效案件服務群組而略過開工問候的案號、紀錄時間與原因。僅已驗證且具 `ORDER_GROUP_READ` 的工會人員可查看。紀錄取自既有稽核事件，獨立於訂金待辦及其件數，既有紀錄仍可在建群後查閱。查詢不建立投遞工作。
- **群組指令**：
  - `綁定訂單 {case_no} {邀請網址}`：具 `ORDER_GROUP_BIND` 且已綁定 LINE 之工會人員輸入（接受單／多空白、全形空白或換行；僅接無額外參數 `https://line.me/ti/g/...` 或 `https://line.me/R/ti/g/...`；儲存至私有 `line_order_group_bindings.invitation_url`）。
  - `發送邀請`：於群組重新檢查資格後為媽媽與所有已綁定指派月嫂排入私人邀請卡片（按鈕開啟群組連結）；發送前群組／網址／訂金／人員變動即自動取消舊工作。
- **開工代班／服務中換人單人邀請（`SSTART-05` / `handover-v1`）**：依 Scheduling 授權對單一已選定且願意承接之月嫂發送原群組連結（不重複邀請全體）；分開回讀「已排入／已送達／失敗／真正入群」。已排班案件的局部代班依 [Scheduling §3.4.1](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction) 辦理。
- **後台群組清單**：每列顯示案號、客戶與月嫂的入群狀況、群組狀態、綁定與最近邀請時間、最近動態及可用操作。完整群組歷程及綁定邀請說明留在抽屜。
- **後台解除綁定**：具 `ORDER_GROUP_BIND` 的工會人員可在「LINE 營運 → 案件群組」的清單操作欄解除綁定。依該列的綁定版本核對目前群組，在同一交易清除目前群組與私人邀請網址、遞增綁定版本，並新增解除事件。保留原案件、綁定與成員歷程。舊群組失去本案小幫手權限，待送群組邀請沿既有機制重新驗證並取消失效工作。解除僅操作後台綁定。
- **永久刪除案件群組歷程**：具 `ORDER_GROUP_BIND` 的工會人員可對已解除綁定的個別案件提交「永久刪除群組歷程」。畫面明示刪除範圍與不可復原。以目前綁定版本重新核對，且在同一交易永久刪除該案所有歷次綁定、解除、群組動態、邀請與成員加入／離開事件，以及舊成員投影。保留案件、LINE 對話、共用稽核與精簡的刪除操作收據。未綁定的版本列僅供阻擋過期操作及後續重新綁定，已清除歷程的案件不顯示在群組工作區。已重新綁定、版本不符或無權的操作不得刪除任何紀錄。
- **LINE 群組解散**：群組解散、官方帳號離群或成員離群均不自動刪除後台歷史紀錄。收到成員離群事件時，沿用既有的成員狀態更新。
- 受限 NAS 的永久刪除經 `lu_nas_delete_order_group_history_v1` 例程執行，僅管理端連線帳號可呼叫。例程與兩個事件刪除 trigger 均核對同案未完成命令及未綁定狀態。既有案件刪除仍由原例程處理。

| 情境（S） | 任務（T） | 操作（A） | 可驗收結果（R） |
| --- | --- | --- | --- |
| 案件有現行綁定，操作者有群組綁定權限 | 解除綁定 | 在清單該案的操作欄送出解除 | 現行群組及邀請網址清除，後台仍可查看歷程，舊群組無法再操作本案小幫手。 |
| 群組綁定在收到確認前已變動，或操作者只有查詢權限 | 保護目前綁定 | 用舊畫面或唯讀帳號提交解除 | 回傳版本衝突或權限拒絕，現行綁定及歷程維持原樣。 |
| LINE 群組已解散或成員離群 | 保留既有紀錄 | 回到後台重新查詢該案 | 歷程仍可查閱。成員離群事件僅更新可辨認的成員狀態。 |
| 案件已解除綁定且有歷程，操作者有群組綁定權限 | 永久刪除該案群組歷程 | 在清單該案的操作欄提交「永久刪除群組歷程」 | 該案群組事件與舊成員投影自資料庫移除，案件與其他案件的紀錄保留。群組清單不再顯示該筆已清除的歷程。 |
| 案件在刪除前已改綁新群組 | 保護目前群組與既有歷程 | 從舊畫面提交永久刪除 | 回傳版本衝突或仍綁定錯誤，群組與其歷程均不受影響。 |

## 4. `LINE-006` 失敗管理、Safe Review Link 與告警退役

- **群組告警與管理員個人 Push 全面退役（`NAS-LINE-03`）**：`設定異常通知群組` 及管理員個人告警 Push（含 `runtime_health_event`、`customer_service_escalation`、`runtime.alert.review_required`、`complaint.ingress.hold_high_ticket`）已正式退役，舊 target 寫入回 `410 Gone`、未寄工作於 provider 前取消。管理員主動於 LIFF 待辦工作台頂端透過唯讀摘要端點 `/api/v1/line/mobile-admin/notification-task-actions/runtime/query`（驗權後回整體／worker 狀態與計數，禁曝錯誤詳情或對象）檢視運行現況（無主動推送案件狀態標 `unknown`）。
- **M4 Safe Review Link**：`IssueSafeReviewLink`／`Redeem`／`Revoke`／`Query` 使用 `issued → redeemed | expired | revoked` 一次性憑證（DB 存 digest＋immutable `runtime_alert_target` 證據，LINE payload 禁夾帶原始 token／URL）。
- **`LINE-006`（`case_no + notification_reason`）**：`LINE Notification` 計算每個適用失敗來源是否皆具備有效 terminal `manual-replay:{source_event_id}:{idempotency_key}` 後繼成功（未取消案件之未送達來源不因設定錯誤失效）；工會可逐筆人工確認略過（`POST /api/v1/line/notification-rules/failures/{issue_key}/skip/{preview|apply}` 寫入綁定 exact owner snapshot token 之 `line.notification.warning_skip` audit 後清除 current issue；來源變更後可重現）。

## 5. Rich Menu、通知文案編輯與表格圖片

- **Rich Menu 草稿與發布 saga**：`QueryRichMenuDraft`／`PreviewRichMenuDraftChange`／`ApplyRichMenuDraftChange` 依 `(menu_definition_id, configuration_revision)` 區分 `editable | processing | published`（published 快照只讀可由此建立下一草稿）；管理台可改背景圖（含 `image_asset_id`／`sha256`／`image_asset_version` 檢查）、按鈕名稱與動作（`uri | message | postback | richmenuswitch` 互斥清空舊欄位），並以 NAS 唯讀預覽結合記憶體即時手機模擬。發布 saga 由 `line_rich_menu_publication_step_acknowledgements`、`attempt_events` 與 `cleanup_anomalies` 保存斷點與冪等重試，發布成功後依角色 fan-out 綁定既有合法身分（不阻擋身分審核原子提交）。Rich Menu API 不送 `X-Line-Retry-Key`。建立請求送出前保存 durable 記錄，已有成功回應時沿用其選單 ID，結果不明時停下來核對官方帳號，避免重複建立。 發布新版本及接續未完成的清理工作時均保留前一版 LINE 選單，清理收據只結束背景工作。前一版仍可能被尚未完成同步的使用者引用。
- **Notification Rules Admin**：規則管理以 `configuration → intent → task` 順序加鎖；禁用未知 event 或 `{} -> {"rules":[]}` 漂移；儲存／停用同交易取消相應排程任務。
- **通知文案編輯器與公版預覽（`LINE-PREVIEW-01～08`、`LINE-COPY-01～05`、`LINE-COPY-EDITOR-01～02`、`LINE-COPY-CATALOG-01`）**：
  - 由 `GET /api/v1/line/message-previews/catalog`、`GET /api/v1/line/message-previews/subjects` 與 `POST /api/v1/line/message-previews/preview` 提供公版索引、對象搜尋與即時渲染；目錄依 `MESSAGE_TEMPLATES` 維護全部通知文字與確認卡片（內文編輯框預設高度 `504px`、正式媒合僅列「正式媒合－客戶完整推薦確認包」，保留各身分獨立成功文案 `identity_bound_customer | _staff | _admin` 與 `PUT` CAS 版本防衝突）。
  - 「通知與發送」工作台使用零寫入公版 `data_source=sample`（`Cache-Control: no-store`，固定範例不含真實個資或發送動作）。「寄送案件資訊」節點以整包呈現，頁面內容見 [媒合候選池規格](02A_媒合候選池與客戶決定及通勤規格.md#31-寄送案件資訊候選詢問與更新詢問期間)。
  - 編輯區依卡片實際欄位提供標題、說明及按鈕名稱的定位入口。即時預覽保留原卡支援的顏色、間距與按鈕樣式。重新渲染草稿時顯示更新狀態，沿用同一則訊息的上次預覽直到新結果到達。預覽中的按鈕只顯示用途，無法執行正式動作。
  - 「通知與發送」的編輯工作台左側呈現直式 LINE 流程圖，依媒合到服務、登記與身分、自助服務與留言及取消與結算分類，各分類按業務步驟排列。展開步驟可直接選擇訊息，中央開啟文案編輯或唯讀內容，右側直接以公版資料呈現即時手機預覽。工作台的中央區僅提供訊息內容維護。切換訊息套用既有草稿保護。流程圖深連結開啟同一工作台，訊息深連結直接定位對應範本與左側步驟。簽約使用外部平台。工會人員回收簽署文件，並可在 LINE 官方帳號聊天後台選用範本手動發送簽署提醒。
  - 未對應流程的範本可在「其他通知」查看。帳務範本深連結定位對應流程與原範本。帳務頁的排程與通知條件入口見 [LINE-PAY-05～07](20_LINE客服與月嫂自助服務正式規格.md#62-繳款提醒與人工收據規範)。
  - 「登記與身分」流程列出身分申請受理通知。「收款與建群」步驟列出客戶回報已匯款時的受理回覆。「取消與結算」流程列出結算明細、退款完成及補收入帳的既有範本，由工會人員在帳務頁依業務進度預覽與手動發送。
- **三張表格圖片渲染（`LINE-COPY-TABLE-01`、`LINE-TABLE-IMAGE-01～04`）**：
  - [候選月嫂的案件資訊](02A_媒合候選池與客戶決定及通勤規格.md#31-寄送案件資訊候選詢問與更新詢問期間)使用表格 PNG 呈現資料。正式推薦一次 Push 只含一則 Flex 輪播訊息，依序呈現各履歷 PNG 頁面、「訂單資訊一、資訊二、每週服務安排」三張表格 PNG。客戶版資訊一的財務欄位限於客戶費用與繳款約定。客戶回覆按鈕放在每週服務安排同一頁。已提交的任務重試時沿用提交時保存的投遞格式。
  - 圖片快照與投遞任務在同一交易提交。`GET /api/v1/line/table-images/{token}` 以七日有效的圖片連結讀取快照，表格按快照渲染，履歷回傳提交時保存的 PNG。履歷連結使用 `LINE_CHANNEL_SECRET`，回應含 `private, no-store, nosniff, no-referrer`。圖片服務異常回 `503`。

## 6. 私人日誌照片媒體傳輸（`NAS-LINE-04`）

- NAS 環境對外日誌照片上傳與下載經專用隔離代理路由 `/internal/v1/line-media/`（由 `line-media-proxy` 憑證驗證原 LINE ID token、目前綁定與本人當日服務權限），公開 DB 帳號對受控附件與日誌主檔嚴格限制唯讀 `SELECT`。
- 本人附件下載 `POST /api/v1/line/staff-self-service/service-day-logs/{log_id}/photos/{file_id}/download` 驗證該日誌附件歸屬後回傳私密 `JPEG/PNG` blob（`no-store/nosniff`，禁止 URL query 傳 token）。

## 7. 驗收標準

| S 情境 | T 任務 | A 操作 | R 可觀察結果 |
|---|---|---|---|
| 已到正式開工日與排程時段，已綁定案件群組，第一期款尚有餘額 | 送開工問候與一期款提醒 | 執行當日通知排程兩次 | 群組只收到一則 `text` Push，含問候、第一期款金額與期限及客戶付款回報指引，無卡片或快選按鈕。客戶私聊無同日首次提醒。 |
| 正式開工時無第一期款或已結清 | 送開工問候 | 執行當日通知排程；另驗證排入後、投遞前才完成核銷 | 群組只收到一則純文字問候，無催繳內容。 |
| 開工日無有效案件群組 | 查詢未能送出的問候 | 執行當日通知排程後，由具群組讀取權限的工會人員開啟「開工問候未送出紀錄」 | 群組和私聊均無 Push。工會讀到案號、紀錄時間與未綁定原因，無對應訂金待辦的案號亦可查閱。 |
| 案件群組已收到開工問候 | 核對開工問候的互動範圍 | 輸入開工服務回報相關文字，另驗證有餘額時本案客戶輸入付款回報文字 | 服務回報文字不觸發開工回覆或建單。客戶付款回報依 LINE-PAY-02 處理。 |
| 有帳務及身分綁定範本 | 從工作台找範本 | 開啟既有帳務範本深連結，再從登記與身分的流程步驟找到綁定通知 | 深連結定位原範本並展開其流程步驟，身分綁定訊息可由左側流程開啟。 |
| 桌面版「通知與發送」已載入流程分類與訊息 | 由流程找到要調整的回覆 | 展開「媒合到服務」的開始服務步驟，開啟延期確認卡，修改文案後點選另一則訊息，分別選擇繼續編輯與捨棄修改 | 左側按順序顯示步驟，中央編輯與較寬的右側預覽同時可見。繼續編輯時保留草稿，捨棄後切換至所選訊息。預覽全程無發送。 |
| 已開啟「雙方合意延期」客戶確認卡 | 核對草稿文案在卡片上的位置 | 依序跳到標題、開頭說明及按鈕，修改各欄內容，再點預覽中的按鈕 | 中央直接顯示文案欄位，公版資料由右側預覽直接帶入。各欄聚焦正確，草稿更新前仍顯示上一版卡片。新版保留原卡樣式並顯示修改後的文案。預覽按鈕只顯示用途，沒有發送或執行業務操作。 |

1. 驗證 Inbox 斷點回滾重試與 `follow/unfollow` 保序、Worker 租約防止重播、群組 `綁定訂單／發送邀請` 與單人代班邀請各階段狀態分離。
2. 驗證 `NAS-LINE-03` 退役端點 410 與 `/runtime/query` 去敏摘要、`LINE-006` 逐來源重播及 skip 解除、Rich Menu 三態草稿與 3-table saga、文案 `504px` 公版預覽、`table-images` 受眾薪資／費用分離，及 `NAS-LINE-04` 跨憑證下載防護。
