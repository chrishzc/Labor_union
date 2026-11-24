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
- **Delivery Task（`pending → processing → sent | retryable_failed | failed | cancelled`）**：
  - Worker 每輪逐筆取得短效未過期租約（預設批大小 25 筆）並於送前重驗未取消；同鍵入列必回既有 task／receipt。
  - 重試、取消與最終失敗工作之結清依 [LINE 異常處理契約](#42-不再寄送與結清)。
  - **業務通知投影規則**：
    - 契約簽署與 LINE 通知分工見 [簽約規格 §3.3](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#33-檔期衝突檢核送交記錄與官方帳號提醒)。
    - **`order.service_start_day`（開工當天群組問候）**：依 Scheduling 確認的正式開工日，在台北時間開工當天依現有開工日通知時段，向本案已綁定的服務群組排入每案一則純文字 Push。依 [LINE-PAY-02](20_LINE客服與月嫂自助服務正式規格.md#62-繳款提醒與人工收據規範)，第一期款有未結清餘額時，才將繳款提醒追加到同一則文字。無第一期款或已結清時仍發送問候。第一期款排程與通用通知規則不得另外排入開工問候或同日第一期首次提醒。重跑排程及重試沿用同一通知識別。送出前重驗正式開工日、群組綁定及第一期款狀態，避免已結清仍催繳。缺有效群組時留供工會查核，不改投私聊；過去開工日不因啟用此通知而補發。`order.pre_start_reminder` 維持停用。
    - `client.second_payment_due`／`client.second_payment_settled`（二期群組通知）：停止投影群組通知，殘留群組工作於投遞前取消。繳款提醒及入帳通知見 [LINE-PAY-03 與 LINE-PAY-08](20_LINE客服與月嫂自助服務正式規格.md#62-繳款提醒與人工收據規範)。
    - `order.service_completed`（完工事件自動投遞）：系統不消費 `line_service_completion_notification` 標記或 Push。規則儲存拒絕，殘留工作於投遞前取消。月嫂從群組小幫手取得問卷的流程依[滿意度調查問卷規格](20_LINE客服與月嫂自助服務正式規格.md#44-滿意度調查問卷)。
    - 服務開始與換人結果日期表：僅發送至本案群組（無「確認／拒絕日期表」按鈕），投遞失敗不回滾正式排班。
    - 案件群組月嫂專屬小幫手選單（含【確認開工日】、【服務排程】、【雙方合意延期】、案件群組留言指引與【客戶常見疑問標準回答】）：月嫂輸入喚醒詞「工會」或「小幫手」及後續各步驟操作（確認單產出、雙方同意、排程查詢、舊協助按鈕的留言指引與標準回答）固定走 `line_webhook_reply` 同步回覆，全程 0 Push 額度消耗。
- **安全觀察端點（Zero Commit／Zero Wakeup）**：
  - `GET /api/v1/line/configurations/{kind}/safe`（僅回傳 `kind`、`revision` 與 `state=empty | configured`，禁洩漏定義、URI 或任何 secret）。
  - Delivery public masked query（限 allowlist 篩選與真實總數分頁，禁止以 `user_id`／payload／raw error 過濾或回傳）。既有付款首次提醒 `client_payment_initial_reminder` 與自動追蹤 `client_payment_automatic_followup` 均投影為既有公開來源類別 `finance`，款項類別篩選與每頁回應使用相同來源資格。未知來源維持 typed `line_delivery_query_invalid_result`、`retryable=false`，不以略過該列或猜測類別交付不完整清單。
  - `GET /api/v1/line/identity/reviews/numbered`（真實 DB `COUNT + LIMIT/OFFSET` 分頁；待審隊列無自動逾期或時間升級，僅限具認證人員依 [身分管理規格](23_LINE身分管理與解除正式規格.md) 手動審核，legacy internal-key-only 審查端點回 `410 Gone`）。

### 2.1 公開工作清單分頁驗收

| 驗收 ID | S：情境與前提 | T：使用者任務 | A：可重現操作 | R：可觀察結果 |
|---|---|---|---|---|
| DELIVERY-QUERY-01 | 工作集合固定且跨越一頁，後頁含首次付款提醒及自動追蹤。 | 查看完整寄送紀錄及款項提醒。 | 依序查第一頁、第二頁、末頁與超出末頁，另查 `category=reminder`、`source_type=finance`。 | 合法提醒均呈現為 `finance`，各頁總數與同一資格集合一致，無工作重複或遺漏，超出末頁回空集合；Query 零寫入、零發送，回應持續遮罩敏感內容。 |
| DELIVERY-QUERY-02 | 查詢結果含未定義的來源。 | 判斷清單是否完整可用。 | 查詢包含該工作的頁面。 | 整次 Query 回 typed unavailable，不洩漏 raw recipient、payload、來源內容或 provider detail，不送訊息、不改 task／receipt。 |

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
- **`LINE-006`（`case_no + notification_reason`）**：LINE 擁有目前失敗來源、投遞結果與人工處置，Anomalies 只消費 typed current predicate。只要通知仍適用，單純修正設定不代表已送達；人工結清依本節辦理。

### 4.1 共用待辦判定與操作資格

- LINE 提供同一份 typed 處理投影，包含明確處理目標、`needs_attention`、`allowed_actions` 與 `blocked_reason`。目標只分為寄送工作及 `LINE-006` 通知異常；有正式來源對應時，投影須指出會處理的原來源及相關工作範圍，沒有來源對應的工作維持單筆 task 目標，不猜測或按案號擴大範圍。
- `needs_attention` 由目前 owner facts、來源適用性、投遞結果及有效人工結清共同決定。原失敗次數、未解決來源 ID 與 attempt 紀錄屬證據，不能單獨覆蓋人工結清判定。通知事項、寄送異常清單、詳情、數量及 Anomalies consumer 使用同一判定；待辦移除不立即刪除寄送紀錄；完整內容與嘗試明細的六個月保存依 §4.4，必要處理憑證另外保留。
- `allowed_actions` 由後端依目前狀態、來源是否啟用及人員原有 capability 計算；前端依此顯示按鈕，Apply 仍 fresh-read 並重新驗權。無可執行操作時顯示原因及核對入口，不以缺少按鈕代替原因。退役來源禁止重試或補送，但已失敗或尚未送出的工作仍可依 §4.2 結清。
- 共用範圍僅為 LINE 異常的判定與操作契約；重用既有 Delivery、manual replay、人工略過、audit、receipt 與 outer Unit of Work。各業務通知資格仍由原 owner 提供，不建立管理全部提醒的 generic failure root、通用業務狀態機或第二套 retry／fallback。
- Query 零寫入、零排送；讀回失敗或不完整須明示，不能當成零筆、已解決或可安全結清。清單的數量與分頁都以相同目前資格計算。正常讀回但本頁零筆且仍有後頁，可以繼續查下一頁；這與讀回失敗或不完整不同。

### 4.2 不再寄送與結清

- 管理端以「不再寄送／結清」表示停止選定範圍的後續投遞並消除待辦。既有 `POST /api/v1/line/notification-rules/failures/{issue_key}/skip/{preview|apply}` 承接通知異常的結清，沿用 exact owner snapshot、PreviewFingerprint 與 `line.notification.warning_skip` audit，不新增平行 token 或處置狀態；單筆工作沿 Delivery 控制入口辦理。兩者同用 §4.1 的目前判定，不另提供只隱藏待辦而繼續寄送的略過方式。
- Preview 顯示案件或工作識別、原來源、納入的工作、目前狀態與操作影響。結清須保存操作者、原因、目標、實際處理範圍、時間及冪等收據；權限沿原 `TASK_CONTROL`／`CONFIG_MANAGE`，跨範圍操作須滿足各項原權限，不因共用介面放寬。
- `pending`／`retryable_failed` 可取消；`failed` 可由人員結清並轉為 `cancelled`。取消只改工作生命週期，保留既有失敗時間、嘗試次數、attempt 結果及稽核，不改成 `sent`，不重做核銷、排班或案件狀態。`sent` 只留寄送紀錄，不提供以結清撤回訊息的操作。
- `processing` 或 provider 結果不明時，一般結清不得回報已安全停送；保留待核對結果與阻擋原因，沿既有租約回收及正式結果核對流程處理後，再依目前狀態結清。worker 與 Apply 同時執行時，依目前租約與狀態驗證，不能把已發生或效果未明的外部呼叫當作未送出。
- 通知異常結清涵蓋 Preview 明示之原來源及其目前未送出重試／manual replay 後繼工作。Apply 在同一 LINE outer Unit of Work 鎖定並 fresh 驗證目前來源與工作；如已進入發送、結果不明或範圍變動，回 typed conflict，不能只隱藏一部分待辦。確認可結清後先取消相關未送出工作，再以取消後的 authoritative readback 保存有效處置及收據，提交後 bounded recheck；不可用本操作自身造成的版本變化製造 stale 或重新開啟待辦。
- 結清後，同一已處置來源不得由排程、retry 或 replay 自動重建寄送工作；送出前亦須核對目前處置。新的業務事件或後續 owner facts 形成新的適用通知時，依正式資格重新判斷，不受前次處置永久封鎖。不得僅憑本次取消造成的任務狀態變化認定有新業務事件，或據此重建寄送工作。
- 批次處理先以明確環境、篩選及分頁預覽固定候選目標，再由人員選定；不按「全部失敗」直接清資料。依 canonical 處理目標去重，每個目標維持原單一 outer commit，回報各項成功、衝突或失敗；重試只接續未成功項目，保留已成功的收據。結清本身不刪除業務資料、來源、attempt、投遞歷史或核銷證據；其後到期整理僅依 §4.4，不刪除核銷及停送憑證。

### 4.3 結清驗收

| ID | S：情境與前提 | T：人員任務 | A：操作 | R：可判定結果 |
|---|---|---|---|---|
| LINE-CLOSE-01 | `failed` 工作仍列待辦，含已退役且禁止重試的來源 | 結清不需補送的通知 | 預覽並確認「不再寄送／結清」 | 有合法結清入口，工作轉 `cancelled` 且待辦移除；零 provider call，失敗 attempt 與處置原因可查 |
| LINE-CLOSE-02 | 同一來源出現在通知異常與寄送失敗清單，含待送的補送工作 | 一次結清原來源 | 由任一入口開啟同一處理範圍並確認，再重查兩份清單及數量、執行 worker | 選定範圍的未送出工作停止；兩份待辦及數量一致移除，寄送歷史保留；worker 不補送 |
| LINE-CLOSE-03 | 原來源缺少映射或 recheck target，但有真實失敗 task | 處理既有工作 | 開啟單筆 task，預覽結清範圍並確認 | 僅結清該 task，不推測其他來源或整案範圍；不因缺映射永久列為無法處理的待辦 |
| LINE-CLOSE-04 | 相同結清命令重送，或 Preview 後工作已進入發送／資料變動 | 防止重複與錯誤結清 | 重送相同冪等鍵，另以變動前 Preview 提交 | 前者回原收據；後者回 typed conflict 且不回報結清成功，沒有部分隱藏或新增補送 |
| LINE-CLOSE-05 | provider 結果不明、讀回不完整或權限不足 | 核對能否結清 | 查清單、詳情並嘗試結清 | 有明確阻擋原因，結果不明或讀回不完整不能假裝零筆或成功；權限不足零 mutation |
| LINE-CLOSE-06 | 原來源已結清，之後又有新的業務事件及適用通知 | 接續新的正常作業 | 重跑原排程，另處理新事件 | 原來源不自動重建寄送工作；新事件依其正式資格建立通知，不因前次結清永久封鎖 |
| LINE-CLOSE-07 | 測試環境有多頁失敗工作，部分目標同源、部分已變動 | 批次結清選定項目 | 預覽並選定目標，執行後重送未成功項目 | 同源目標不重複處理，各項結果及收據可讀回；變動項目回衝突，未選項目及其他環境不受影響 |


### 4.4 寄送紀錄六個月滾動保存

- 使用者核定完整寄送內容與嘗試明細滾動保留六個月。以目前時間轉 Asia/Taipei 後向前六個日曆月計算 cutoff，月末不存在同日則取該月最後一日，保留時分秒；轉 UTC 與資料庫比較。嚴格早於 cutoff 才到期，恰在邊界仍保留。
- 只有 `sent`／`cancelled` 且最後更新時間與所有 attempt 完成時間均早於 cutoff、所有租約欄位空、寄送結果已確認者可整理。`pending`／`processing`／`retryable_failed`／未解決 `failed`、目前或最後 attempt 尚有 `line_reply_outcome_uncertain`、linked intent 尚未到相符終態及未來時間一律保留。例如一筆待重試工作即使已建立超過六個月，也仍保留；只有符合本段全部條件才可整理，不只看建立時間。
- 到期同交易刪除該工作 attempt 明細，將 task 與所有 linked notification intent 完整 payload 替換為明確 `_retention_expired=true` 標記，移除 task 長錯誤說明。不得僅隱藏 UI 而保留相同正文副本。line inbox 的入站內容、業務來源與其他 Domain facts 不屬本次寄送紀錄清理範圍。
- task 精簡主列保留原 ID、recipient/source 身分、原 payload fingerprint、idempotency/correlation key、終態、時間與累計嘗試數，供既有 source linkage、付款已通知及防重送核對；不變更原 fingerprint 或原最後更新時間。LINE command receipts、audit、人工結清原因、綁定誤報消除及來源停送憑證不刪除。這些是必要操作證據，不能當成可復原完整內容的歷史。
- 清理屬 LINE owner 維護工作，沿 canonical worker 的 additional worker 接線，每輪有界最多 25 筆候選，每筆 fresh lock task、attempt 與 intent，由一個 outer UoW 保存精確 task/cutoff 清理憑證、執行刪除與去內容化、提交；失敗 rollback 該筆，不產生 provider call。舊資料庫須先套正式 additive guard migration，禁止關閉既有 append-only trigger。
- attempt DELETE 只接受精確 session command key 對應 durable `line_command_receipts` 的 `line-delivery-retention:<task_id>` result_reference，snapshot task_id/cutoff 一致，且 DB fresh task 仍為無租約的合法終態、最後更新及該 attempt 完成時間早於 cutoff；保留原 registry-delete 例外。session command key 於 finally 清除，不以無憑證旗標開放刪除。
- 清理後列表及總數同時排除到期標記，直接開啟舊 detail 回 typed `410 line_delivery_history_expired`，顯示內容與明細已到期，而非假空白或泛用 500。既有工作鍵 enqueue 仍回同 task，不重建、不重新發送；原圖片下載不再提供已清除內容；原來源或其精確 replay 內容已到期時，Preview／Apply 拒絕以舊來源補送，回 `notification_source_history_expired`，新業務事件仍按目前資格判斷。尚未處理的異常不受六個月限制。
- 重跑略過已整理 task，不新增重複憑證。DB 備份可能包含當時尚未到期的內容，依 [NAS 備份保存](10A_NAS_Fresh初始化與維護復原規格.md#52-每日排程備份滾動保存) 管理；本節不回寫或刪除既有備份，也不自動還原內容。

| ID | S | T | A | R |
|---|---|---|---|---|
| LINE-RET-01 | 六個月前後及月底、跨年工作同時存在 | 按六個日曆月整理已完成歷史 | 固定臺灣時鐘，執行 worker 並讀回 task、attempt、intent | 嚴格早於 cutoff 的合法終態去正文及明細，邊界與新工作不變；所有正文副本同步整理 |
| LINE-RET-02 | 待送、處理中、重試、未解決失敗或結果不明已超過六個月 | 保留仍需處理的工作 | 執行相同清理 | payload、attempt、狀態與待辦不變；不發送 LINE |
| LINE-RET-03 | 工作已到期整理、來源已人工結清 | 防止清理後重送與誤報復活 | 用原鍵 enqueue、重跑清理、查詢兩份待辦與舊 detail | enqueue 回同 task，重跑零重複整理；停送／消除憑證保留；舊 detail typed410，列表count/items一致排除 |
| LINE-RET-04 | 刪除命令缺憑證、task/key不符、未到期或尚有租約 | 維持 DB 防刪保護 | 真 MySQL 執行正負 scoped DELETE 並注入中途失敗 | 只有合法到期精確 task 可刪；負例拒絕且無部分清理，原 registry-delete保護仍有效 |

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
  - [候選月嫂的案件資訊](02A_媒合候選池與客戶決定及通勤規格.md#31-寄送案件資訊候選詢問與更新詢問期間)使用表格 PNG 呈現資料。正式推薦的月嫂連結、案件資訊與回覆按鈕依[客戶確認包契約](02A_媒合候選池與客戶決定及通勤規格.md#32-客戶推薦確認手動更正與服務前整案換人r-04)組合。已提交的任務重試時沿用提交時保存的投遞格式。
  - 圖片快照與投遞任務在同一交易提交。`GET /api/v1/line/table-images/{token}` 以七日有效的圖片連結讀取快照，表格按快照渲染。既有已提交的履歷圖片任務仍讀提交時保存的 PNG；圖片連結維持既有簽章驗證，回應含 `private, no-store, nosniff, no-referrer`。圖片服務異常回 `503`。月嫂個人網頁不經此圖片快照端點提供。

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
