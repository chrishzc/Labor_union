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
- `caregiver`：服務人員／月嫂。
- `union_staff`：工會官方與監督方。

Rich Menu 現為三組：一般客戶、月嫂、工會人員。工會人員 Menu 預留客服系統與月嫂驗證管理入口。

## 月嫂六位數驗證流程

```text
使用者輸入「我是月嫂」
  -> 後端產生密碼學安全的 6 位數字
  -> 保存 10 分鐘、最多 5 次嘗試
  -> 工會內部接口查詢有效驗證碼
  -> 工會服務人員告知月嫂
  -> 月嫂在 LINE 輸入驗證碼
  -> 驗證成功後 role=caregiver
  -> Worker 綁定月嫂 Rich Menu
```

內部接口必須帶 `X-Internal-API-Key`，其值對應 `.env` 的 `INTERNAL_API_KEY`：

```text
GET /api/line/caregiver-verifications
PUT /api/line/users/{user_id}/role/{role}
```

正式客服登入與角色權限完成後，應以管理員 Session／Passkey 取代或包覆此內部金鑰。

## 後續事項

- 工會客服入口目前為 Rich Menu 靜態 Action；待客服 Web／LIFF 系統完成後再改為受保護 URL。
- LINE 影像與 Rich Menu 圖片仍建議使用 R2／S3／MinIO 或 NAS，MySQL 後續新增 `media_assets` 保存中繼資料。
- 正式部署前替所有 `/api/config` 管理接口加入管理員驗證；Rich Menu 發布權限不可公開。
- 若 FastAPI 改成多程序或多主機，`asyncio.Event` 要改成 Redis／RabbitMQ 等跨程序通知。

