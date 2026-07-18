# LINE Bot 後端重構：Webhook 安全、可靠排程 Worker、三角色驗證與伺服器監控

## PR 摘要

本次更新將原本集中在 `line/main.py` 的 FastAPI、LINE Webhook 與背景任務拆分成獨立模組，加入 LINE Webhook 簽章驗證、事件去重、可重試的排程 Worker，以及一般客戶、月嫂、工會人員三種 LINE 身分。

同時將 LINE／LIFF 的文字、圖文選單及客服靜態內容整理成可由前端串接的 JSON 設定 API，並強化本機開發啟動器，使 FastAPI 與 ngrok 能互相監控、同步關閉及由開發者選擇重新啟動。

本文件涵蓋目前分支相較 `origin/LINE-Bot-Wen` 尚未 Push 的三個提交：

- `b21062f`：新增 FastAPI 主入口、資料庫 Schema 與 LINE 程式重構。
- `f92a1ad`：LINE／LIFF JSON 設定重構。
- `94e1e36`：Webhook 安全、事件去重與伺服器監控。

## 主要新增功能

### 1. FastAPI 與 LINE 模組拆分

- `api/main.py` 成為正式 FastAPI ASGI 主入口。
- `line/line_bot.py` 負責 LINE Webhook、LIFF、Rich Menu 與 LINE 相關 API。
- `line/worker.py` 負責 LINE Push、Rich Menu 操作、ChromaDB／RAG 及排程任務。
- `line/main.py` 保留為舊匯入相容層。

### 2. LINE Webhook 安全與可靠性

- 使用原始 HTTP body、Channel Secret 與 HMAC-SHA256 驗證 `X-Line-Signature`。
- 無效簽章回傳 HTTP 401，不解析事件、不接觸資料庫。
- 使用 `webhookEventId` 保存事件並去重，避免 LINE 重送造成重複任務。
- 成功事件標記為 `completed`；處理失敗會 rollback 並回傳 HTTP 500。
- Webhook 不再同步執行 LINE API 或 ChromaDB，改為寫入任務後喚醒 Worker。

### 3. 可靠排程 Worker

- 支援立即任務與 `scheduled_at` 未來排程。
- 使用 transaction 與 `FOR UPDATE SKIP LOCKED` 領取任務。
- 任務狀態包含 `pending`、`processing`、`sent`、`failed`、`cancelled`。
- 支援 idempotency key、LINE Retry Key、錯誤紀錄及指數退避重試。
- Worker 啟動時可恢復卡住超過 10 分鐘的 `processing` 任務。
- Webhook commit 後立即喚醒 Worker，另保留 60 秒低頻掃描作為通知遺失保底。
- 排程依 `Asia/Taipei` 計算並以 UTC 寫入資料庫。

### 4. 新好友與封鎖生命週期

- `follow`：建立／更新 LINE 使用者、建立歡迎訊息與 D+1、D+2、D+3 任務。
- `unfollow`：將使用者標記為 `blocked`，取消尚未發送的新好友排程。
- D+1～D+3 文案與時間由 JSON 設定管理。

### 5. 三種 LINE 使用者角色

- `customer`：一般需求方／媽媽。
- `caregiver`：服務人員／月嫂。
- `union_staff`：工會官方／監督人員。
- Rich Menu 擴充為一般客戶、月嫂與工會人員三組。
- 工會人員選單預留客服系統與月嫂驗證管理入口。

### 6. 月嫂六位數驗證

- 使用者輸入「我是月嫂」時，不再直接切換身分。
- 後端以安全隨機方式產生六位數驗證碼。
- 驗證碼有效 10 分鐘，最多輸錯 5 次。
- 驗證成功後才把角色改為 `caregiver`，並由 Worker 綁定月嫂 Rich Menu。
- 開發環境可在 FastAPI 終端顯示驗證碼；正式環境設定 `APP_ENV=production` 後強制不顯示。
- 驗證碼查詢及角色管理接口以 `X-Internal-API-Key` 保護。

### 7. JSON 設定與前端預留 API

- 統一管理 Webhook 回覆、推播、排程及客服常用文字。
- Rich Menu 支援尺寸、顏色、圖片、按鈕範圍及 message／URI／LIFF／postback Action。
- LIFF 支援頁面文字、主題與動態欄位設定。
- 私人客服先提供服務時間、狀態及固定文字設定；聊天資料尚未建立 MySQL 功能。
- JSON 寫入採暫存檔加 `os.replace` 原子替換，降低設定檔寫入中斷風險。

### 8. 開發伺服器共同監控

- `start_line_bot.py` 同時啟動並監控 FastAPI 與 ngrok。
- 任一服務停止時會顯示故障服務與 Exit Code，並關閉另一個服務。
- ngrok 日誌改以 `[ngrok]` 前綴顯示，不再丟棄錯誤輸出。
- 開發終端會詢問：

```text
是否要重新啟動 ngrok & FastAPI？(y/n):
```

- `y`：由同一監控程序重新建立兩個服務。
- `n`：關閉監控，之後需手動啟動。
- 可透過 `ENABLE_SERVER_FAILURE_POPUP=true` 改用「重新啟動／關閉」Windows 彈窗。
- 正常 `Ctrl+C` 不會視為異常，也不會自動重啟。

## 新增檔案

| 檔案 | 功能 |
|---|---|
| `api/main.py` | 正式 FastAPI App 與 lifespan 主入口，掛載各 API Router、靜態檔案及 Worker。 |
| `api/schemas/line_config.py` | LINE 訊息範本、Rich Menu、LIFF、排程及客服 JSON 的 Pydantic 驗證模型。 |
| `config/customer_service.json` | 私人客服服務時間、狀態與固定文字的靜態設定。 |
| `config/message_schedules.json` | 新好友 D+1～D+3 排程及時區設定。 |
| `config/message_templates.json` | Webhook、Push、排程與客服共用訊息範本。 |
| `docs/line_stage4_4_5_report.md` | 第四階段與 4.5 架構、安全及角色流程報告。 |
| `line/line_bot.py` | LINE Webhook、LIFF、角色驗證與 LINE API Router。 |
| `line/security.py` | LINE Webhook HMAC-SHA256 簽章驗證。 |
| `line/worker.py` | LINE 任務鎖定、排程、RAG、發送、重試與錯誤處理。 |
| `services/json_config_service.py` | JSON 白名單讀寫、驗證及原子替換服務。 |
| `services/line_task_service.py` | 統一建立具有排程、payload 與冪等鍵的 LINE 任務。 |
| `services/webhook_event_service.py` | Webhook 收件紀錄與 `webhookEventId` 去重。 |

## 修改檔案

| 檔案 | 修改內容 |
|---|---|
| `.env.example` | 新增 LINE、內部 API、開發驗證碼顯示及伺服器異常彈窗相關環境變數範例。 |
| `api/routes/line_system_config.py` | 重構訊息範本、Rich Menu、LIFF、客服與排程設定 API。 |
| `config/README_CONFIG.md` | 補充 JSON 格式、API、媒體儲存建議與安全注意事項。 |
| `config/liff_settings.json` | 調整 LIFF 主題、頁面文字與動態欄位結構。 |
| `config/line_menu.json` | 改為多組 Rich Menu，新增工會人員選單。 |
| `db/schema.sql` | 擴充 `line_tasks`，新增 `line_webhook_events`、`line_users` 與統一的 `line_confirmation_requests`。 |
| `line/LINE_Bot_SOP.md` | 更新三角色、六位數驗證、Worker 與 Rich Menu 流程。 |
| `line/setup_rich_menus.py` | 依新 JSON 結構動態產生圖片、LINE Action 與 Rich Menu ID。 |
| `line/start_line_bot.py` | 改為 FastAPI/ngrok 一鍵啟動、雙程序監控、終端 y/n 與可選錯誤彈窗。 |
| `online.bat` | 正式 FastAPI 啟動入口改為 `api.main:app`，移除正式環境 `--reload`。 |
| `README.md` | 更新 FastAPI 啟動入口與模組說明。 |
| `CHANGES_UI_CHANG.md` | 更新 UI／後端變更說明。 |

## 刪除檔案

| 檔案 | 原因 |
|---|---|
| `config/webhook_replies.json` | 功能已合併至較完整的 `config/message_templates.json`，避免兩份回覆文字不同步。 |
| `line/main.py` | 舊 FastAPI 相容入口已無正式執行依賴；測試改用 `api.main` 後安全移除。 |

## 資料庫異動

### `line_tasks` 擴充

- 任務類型 `task_type`。
- 非文字任務參數 `payload_json`。
- 執行時間 `scheduled_at`。
- 鎖定時間 `processing_started_at`。
- `retry_count`、`max_retries`、`next_retry_at`。
- `sent_at`、`failed_at`、錯誤代碼與錯誤內容。
- `line_request_id`、`source_event_id`、`idempotency_key`。

### 新增資料表

- `line_webhook_events`：Webhook 收件、狀態與事件去重。
- `line_users`：LINE 好友狀態與三種角色。
- `line_confirmation_requests`：統一保存月嫂六位數驗證與客戶重新綁定確認請求。

本次已使用 `scripts/init_db.py` 重建開發資料庫並成功執行 Schema。正式環境不可直接執行會清除資料的初始化流程，需另行建立 migration。

## 新增環境設定

```env
LINE_CHANNEL_SECRET=your_line_channel_secret_here
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token_here
INTERNAL_API_KEY=replace_with_a_long_random_internal_api_key

APP_ENV=development
SHOW_CAREGIVER_VERIFICATION_CODE=true
ENABLE_SERVER_FAILURE_POPUP=false
```

正式環境至少應設定：

```env
APP_ENV=production
SHOW_CAREGIVER_VERIFICATION_CODE=false
ENABLE_SERVER_FAILURE_POPUP=false
```

## 測試與驗證

- Python `compileall` 語法檢查通過。
- LINE Webhook 無效簽章回傳 401。
- 正確簽章 Webhook 回傳 200。
- `webhookEventId` 重複事件去重測試通過。
- follow、D+1～D+3、月嫂驗證、角色切換及 unfollow 取消排程測試通過。
- Worker mock 發送成功後轉為 `sent`。
- 模擬 LINE HTTP 503 後，任務轉回 `pending`、增加重試次數並產生下次重試時間。
- JSON、Pydantic 設定與內部 API 金鑰驗證通過。
- FastAPI/ngrok 程序相依清理測試通過。
- 終端 y/n 重啟、關閉及無效輸入流程測試通過。
- 測試資料已清除，沒有建立一次性 Python 測試檔案。

## PR 審查注意事項

1. LINE Developers 的 Webhook URL 必須包含 `/webhook/line`，不可只填 ngrok 根網址。
2. 新增或變更 Rich Menu JSON 後，需要執行發布程序才會在 LINE 生效；工會選單 ID 會在發布後建立。
3. `GET /api/line/caregiver-verifications` 與角色修改 API 必須帶 `X-Internal-API-Key`。
4. `/api/config` 管理 API 尚需在正式公開前接上完整管理員登入與角色權限。
5. 現在使用 ngrok 作為開發 Tunnel；Cloudflare Tunnel、正式常駐與外部健康監控預計在第五階段處理。
6. `asyncio.Event` 適用目前單一 FastAPI 程序；未來改成多程序／多主機時需換成 Redis 或訊息佇列。

## UTF-8 編碼統一（2026-07-18）

- 新增 `.editorconfig` 與 `.gitattributes`，統一專案文字檔為 UTF-8 無 BOM。
- 將 `line/line_bot.py` 的 UTF-8 BOM 移除。
- 將 `line/test_result.txt` 從 UTF-16 LE 轉為 UTF-8。
- 修復資料字典中的損壞字元。
- Windows 開發／正式批次檔統一切換至 Code Page 65001，並設定 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
- Python 啟動、初始化、匯入與監控腳本同時設定 stdout、stderr 為 UTF-8。

## 工作人員統一待審與開發終端審核（2026-07-18）

- 新增 `/api/line/staff/review-requests`，讓工會前端以同一接口取得月嫂驗證與客戶重新綁定待審事項。
- 新增統一 approve／reject 路由；月嫂核准後才對工作人員回傳驗證碼，拒絕則取消驗證碼並通知申請者。
- 舊版重新綁定接口保留，但全面加入 `X-Internal-API-Key`。
- `start_line_bot.py` 新增非阻塞重新綁定終端審核；開發者可輸入 `y` 核准或 `n` 拒絕，且共用正式 API 業務邏輯。
- 新增 `ENABLE_REBIND_CONSOLE_REVIEW`，正式環境會自動停用終端人工審核。

## FastAPI 單一入口整理（2026-07-18）

- 移除舊的 `line/main.py` 相容層，FastAPI 啟動入口統一為 `api.main:app`。
- 更新兩個仍引用舊入口的測試，LINE 函式改為直接從 `line.line_bot` 匯入。
- 同步修正 `system_map.md`、`system_map.yaml` 與 `CHANGES_UI_CHANG.md` 的過時入口資訊。

## Schema 文件一致性修正（2026-07-18）

- 修正 `db/schema.sql` 在第 25 項後倒退至第 20 項的註解編號，後續物件改為連續的第 26～32 項；資料庫結構未改變。
- 修復資料字典第 46 行附近的客戶／BeClass 表格混接與欄位重複問題。
- 依現行 Schema 同步 `clients`、`beclass_records`、`staff` 欄位內容。
- 將資料表總覽補齊至 31 張資料表與 1 個 View，並補充排班、帳務及 LINE 資料表用途。
- 移除對不存在之 `data_anomaly_events` 資料表的錯誤敘述。
- 已確認 1～32 項連續、32 個 Schema 物件全部被文件涵蓋、Markdown 表格格式正確。

## 確認請求 DB 統一（2026-07-18）

- 將月嫂驗證與客戶重新綁定統一保存於 MySQL `line_confirmation_requests`。
- 月嫂驗證碼仍於申請時立即產生，工作人員確認接口取得既有驗證碼，原操作流程不變。
- 重新綁定申請不再寫入 `config/rebind_requests.json`，核准與拒絕改以 transaction、資料列鎖及狀態欄位處理。
- 保留既有重新綁定與統一待審 API 網址，前端及開發終端審核器不需重新串接。
- 刪除空的 `config/rebind_requests.json`，同步更新設定、SOP、階段報告與資料字典。
- 已重建開發 DB，並驗證重新綁定核准／拒絕、統一待審、月嫂驗證碼查看及有效簽章 Webhook 的完整月嫂角色切換流程；測試資料已清除。

## LINE 月嫂角色統一與人工核准（2026-07-18）

- 將LINE月嫂角色從`caregiver`統一為既有資料模型使用的`staff`，並同步Schema、Python、Rich Menu、訊息範本與文件。
- 使用者輸入「我是月嫂」後建立`staff_verification`待審請求，不再產生六位數驗證碼。
- 工會人員按下核准即直接完成身分確認、把`line_users.role`改為`staff`，並由Worker綁定月嫂專屬選單。
- 開發模式使用`ENABLE_LINE_REVIEW_CONSOLE`控制終端`y/n`審核；正式模式強制停用終端審核，Web/UI可串接相同的受保護approve／reject API。
- 開發啟動器會在未設定內部金鑰時建立單次程序隨機金鑰，不保存到`.env`；正式環境仍必須自行設定`INTERNAL_API_KEY`。
- 已重建開發Schema並完成有效簽章Webhook、待審、核准、角色與請求狀態整合測試；測試資料已清除。

### 開發終端審核改為事件推送

- 移除每3秒查詢待審API的固定輪詢與大量`GET /api/line/staff/review-requests`存取紀錄。
- `start_line_bot.py`在開發期間建立loopback-only的一次性通知入口；Webhook提交待審資料後立即推送一筆事件。
- 終端收到事件後才載入該筆資料並顯示`y/n`；啟動時僅補查一次既有pending請求。
- 通知入口使用單次程序內部金鑰，不公開到ngrok；正式Web/UI接口與資料庫待審機制不變。
