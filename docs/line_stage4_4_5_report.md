# LINE Bot 第四階段與 4.5 實作報告

## 目標與完成狀態

第四階段先保護 Webhook 入口與任務可靠性；4.5 再把 Webhook 內的 LINE API、ChromaDB 等耗時工作移到 Worker，並建立三種 LINE 使用者角色。

```text
LINE
  -> FastAPI /webhook/line
     -> 讀取原始 body
     -> 驗證 X-Line-Signature
     -> webhookEventId 去重
     -> transaction 寫入事件、使用者與任務
     -> commit、喚醒 Worker、回 200

Worker
  -> 鎖定到期任務 pending -> processing
  -> LINE Push / Rich Menu / ChromaDB RAG
  -> 成功 sent
  -> 暫時失敗 pending + 指數退避
  -> 永久失敗 failed
```

## 簽章驗證：使用前後

以前只要知道公開 Webhook URL，就可以偽造 LINE JSON 送入商業邏輯。現在 FastAPI 先保留原始 request body，使用 `LINE_CHANNEL_SECRET` 計算 HMAC-SHA256，再做 Base64 與 `X-Line-Signature` 的固定時間比較。缺少 Secret、缺少簽章或比對失敗一律回 401，不接觸 DB 與 Worker。

簽章正確後才解析 JSON。處理失敗會 rollback 並回 500，讓 LINE 的重新投遞機制有機會重送；成功事件以 `webhookEventId` 唯一鍵去重並標記 `completed`。

## 任務可靠性

- `line_tasks` 支援任務類型、JSON payload、排程、鎖定時間、重試次數、下次重試時間、錯誤、LINE request ID 與 idempotency key。
- Worker 使用 transaction 與 `FOR UPDATE SKIP LOCKED` 領取任務，避免多個執行器重複處理同一筆。
- LINE Push 使用固定 `X-Line-Retry-Key`；408、425、429 與常見 5xx 採指數退避。
- Worker 啟動時恢復卡住超過 10 分鐘的 `processing` 任務。
- Webhook 通知是主要喚醒方式；每 60 秒低頻掃描一次作為通知遺失保底，不再每 2 秒輪詢。

## 好友生命週期與排程

- `follow`：建立或更新 `line_users`、排入歡迎訊息與 D+1、D+2、D+3。
- 排程設定位於 `config/message_schedules.json`，文案引用 `config/message_templates.json`。
- 顯示時區使用 `Asia/Taipei`，寫入 MySQL 前轉成 UTC，避免主機或 DB 時區造成偏移。
- `unfollow`：標記 `blocked`，取消尚未送出的 onboarding 任務。

## 4.5：耗時工作與三種角色

Webhook 不再同步呼叫 LINE API 或 ChromaDB。一般文字建立 `rag_reply`；圖文選單建立 `rich_menu_link`／`rich_menu_unlink`；由 Worker 實際執行。

`line_users.role`：

- `customer`：一般需求方／媽媽。
- `staff`：服務人員／月嫂，與資料庫 `staff` 主表統一。
- `union_staff`：工會官方與監督方。

Rich Menu 現為三組：一般客戶、月嫂、工會人員。工會人員 Menu 預留客服系統與月嫂驗證管理入口。

## 月嫂人工確認流程

```text
使用者輸入「我是月嫂」
  -> 建立 staff_verification 待審請求
  -> 工會服務人員在開發終端或正式 Web/UI 核准
  -> 核准後 role=staff
  -> Worker 綁定月嫂 Rich Menu
```

內部接口必須帶 `X-Internal-API-Key`，其值對應 `.env` 的 `INTERNAL_API_KEY`：

```text
GET /api/line/staff/review-requests?request_type=staff_verification
POST /api/line/staff/review-requests/staff_verification/{request_id}/approve
POST /api/line/staff/review-requests/staff_verification/{request_id}/reject
PUT /api/line/users/{user_id}/role/{role}
```

正式客服登入與角色權限完成後，應以管理員 Session／Passkey 取代或包覆此內部金鑰。

## 後續事項

- 工會客服入口目前為 Rich Menu 靜態 Action；待客服 Web／LIFF 系統完成後再改為受保護 URL。
- LINE 影像與 Rich Menu 圖片仍建議使用 R2／S3／MinIO 或 NAS，MySQL 後續新增 `media_assets` 保存中繼資料。
- 正式部署前替所有 `/api/config` 管理接口加入管理員驗證；Rich Menu 發布權限不可公開。
- 若 FastAPI 改成多程序或多主機，`asyncio.Event` 要改成 Redis／RabbitMQ 等跨程序通知。

## 第五階段 5.1：LINE 管理中心安全入口

5.1 已將既有 Streamlit UI 接到 FastAPI 的 LINE 管理入口骨架：

```text
管理員瀏覽器
  -> Streamlit（伺服器端保存內部金鑰）
  -> X-Internal-API-Key + Bearer Session
  -> FastAPI 管理員驗證與角色權限
  -> LINE 設定／Worker 狀態／後續人工審查 API
```

- 新增 `admin_users`、`admin_sessions`、`admin_audit_logs`。
- Session 預設 30 分鐘，可由 `ADMIN_SESSION_MINUTES` 調整；登出後立即撤銷。
- 角色依序為 `line_viewer`、`line_agent`、`line_manager`、`system_admin`。
- LINE 管理中心 5.1 先提供登入、系統健康、Worker／DB／LINE 金鑰設定狀態與後續分頁骨架。
- 訊息管理、排程、Rich Menu、LIFF、人工審查、客服與稽核頁會在後續 5.x 逐頁接上現有 API。
- 第六階段換用 LINE 官方 SDK 時只替換 LINE 邊界實作；管理員驗證、CORS、Session、RBAC 與稽核不由 SDK 提供，會繼續保留。

## 第五階段 5.2：訊息管理中心

- Streamlit 訊息管理頁已接上 FastAPI 與 `message_templates.json`。
- 支援範本搜尋、篩選、新增、修改、複製、文字／Flex JSON 預覽、啟停與二次確認刪除。
- 以 SHA-256 內容 revision 與 `If-Match` 防止舊畫面覆蓋其他管理員的新修改。
- 啟用中的 D+1～D+3 排程引用範本時，後端拒絕停用或刪除並回傳引用排程與天數。
- 訊息異動寫入 `admin_audit_logs`，保存動作、範本 ID 與非敏感摘要；單純預覽不記為異動。
- 範本修改只影響之後的 Webhook 與新建立任務；已存在 `line_tasks` 的訊息快照不回溯修改。

## 第五階段 5.3：排程與 Worker 任務管理

- 「排程任務」頁已接上 D+N onboarding 排程編輯器，可設定 IANA 時區、D+天數、發送時間、
  範本、啟停與重新加入好友是否重跑。
- 排程設定使用 revision／`If-Match` 與同程序寫入鎖，舊畫面修改會回 409；只允許引用啟用中的範本。
- 排程變更只影響後續 follow 建立的新任務；既有 `line_tasks` 保存原時間與訊息快照。
- 任務管理提供統計、篩選、分頁、內容明細與人工取消、立即執行、失敗重試；每個操作均受 RBAC、
  資料列狀態鎖及 `admin_audit_logs` 保護。
- 新增 `line_task_attempts`，逐次保存 Worker 執行序號、結果、是否可重試、錯誤、LINE request ID
  與起訖時間，便於客服判斷任務為何失敗。
- UI 日期以 `Asia/Taipei` 顯示，資料庫仍保存 UTC；「今日成功」亦依台北日界統計。
- 管理頁只在載入、操作或手動重新整理時查詢，不使用 3 秒固定輪詢。Webhook、人工立即執行與
  重試會喚醒 Worker，既有低頻掃描僅作通知遺失的容錯。

## 第五階段 5.4：Rich Menu 管理中心

- 三種選單加入 `audience_role`，固定對應 `customer`、`staff`、`union_staff`；預設選單只能屬於 customer。
- 管理 UI 可編輯名稱、尺寸、顏色、按鈕範圍與 Action，支援自動產圖、安全圖片上傳及預覽。
- Rich Menu JSON 使用 revision／`If-Match` 防止舊畫面覆蓋新版；按鈕越界、重疊與非 HTTP(S) 網址會被拒絕。
- 新增 `media_assets`，圖片本體存受控檔案系統／NAS，DB 僅存路徑、尺寸、MIME、SHA-256 等中繼資料。
- 新增 `line_rich_menu_publications`，保存發布快照、狀態、LINE Menu ID、圖片、重試與錯誤；發布失敗不替換舊版。
- Worker 一次只發布指定 Menu；發布成功後，staff／union_staff 使用者會收到具冪等鍵的重新綁定任務。
- `line_bot.py` 優先從 MySQL 讀取目前發布 ID，`rich_menu_ids.json` 暫時保留過渡相容。
- Worker 首次啟動會把 JSON 內既有 ID 登記為目前版本，不會重新發布或呼叫 LINE。
- 管理頁只在操作或按下重新整理時讀取發布紀錄，不使用固定輪詢。

## 工作人員統一待審接口補充

月嫂身分確認與客戶重新綁定共用 MySQL `line_confirmation_requests`，並提供統一的 `/api/line/staff/review-requests` 介面，供未來工會客服前端顯示同一份待處理清單。月嫂申請由工會人員核准後直接切換身分，不產生驗證碼。所有工作人員接口均要求 `X-Internal-API-Key`。

開發環境由專案根目錄的`start_fastapi_ngrok.py`建立只綁定`127.0.0.1`的一次性通知入口。Webhook成功提交月嫂身分或客戶重新綁定申請後，直接推送一筆通知，終端立即顯示`y/n`並呼叫同一組正式approve／reject API；不再每3秒查詢待審API。啟動時只掃描一次既有待審資料，避免服務重啟期間的申請被遺漏。

## 第五階段 5.6：人工審查中心

- 新增正式管理接口 `/api/v1/line/review-requests`，提供統計、分頁篩選、詳細資料、核准與拒絕。
- `line_agent` 可查看，`line_manager` 才能做決定；拒絕原因必填，核准可留下稽核備註。
- `line_confirmation_requests` 新增 Web 管理員 ID 與決定原因，並以可重跑 Schema part 升級既有資料庫。
- 月嫂認證及客戶重新綁定集中到 `services/line_review_service.py`，正式 UI 與開發終端不再各自維護交易邏輯。
- 處理前以 `SELECT ... FOR UPDATE` 鎖定申請；已處理申請回 409，不會重複建立 LINE 任務。
- 重新綁定核准前重新檢查舊綁定快照、新 LINE 衝突及案件編號，資料在等待期間改變時拒絕覆蓋。
- 核准／拒絕結果先與 LINE 任務一起提交，再喚醒 Worker；月嫂拒絕狀態統一為 `rejected`。
- 管理清單遮蔽 LINE ID，詳細頁才顯示完整值；UI 不固定輪詢，只在操作或手動重新整理時查詢。
- 開發終端維持啟動時一次補查及 Webhook／LIFF 即時推送的 `y/n` 操作，舊接口作為相容包裝保留。
