# Work Log
## [2026-07-12]
- 刪除 `.env` 中未使用的環境變數 `END_POINT`。
- 更新 `.env.example` 中的 `DB_PORT` 預設值為 `3307`，以與 `docker-compose.yml` 保持一致。
- 將 LINE Bot 綁定邏輯從「直接覆蓋」改為「後台人工審核」，建立暫存檔 `config/rebind_requests.json`，並新增前端串接 API 與文件。
- 新增 `api/routes/line_system_config.py`，提供動態管理 LIFF 外觀、Webhook 回覆及圖文選單的 RESTful API，並實作圖文選單自動更新機制。
- 修復 `line/setup_rich_menus.py` 舊版設定管理器 (`admin.settings_manager`) 引用缺失問題，將選單 ID 改存於本地 `config/rich_menu_ids.json`。
- 修改 `line/main.py` 以讀取本地 JSON 取得最新的月嫂與預設選單 ID，完成選單切換修復。

## [2026-07-13]
- 於 `db/schema.sql` 新增 `line_tasks` 及 `system_alerts` 兩張資料表定義。
- 將 `line/main.py` 內所有對 `line_push_tasks` 的參照修正為 `line_tasks`。

## [2026-07-15]
- 解決 `git pull origin main` 所產生的檔案合併衝突 (`db/schema.sql`, `line/main.py`, `start.bat`)。
- 在產生衝突的程式區塊加入逐行註解，解釋解決衝突的原因與決策邏輯。
- 修正 `line/start_line_bot.py` 在 Windows 環境下輸出 Emoji 導致 `UnicodeEncodeError` 崩潰的問題，透過設定 `sys.stdout.reconfigure(encoding='utf-8')` 解決。

## [2026-07-16]
- 整理並新增 `document/line bot 簡報大綱.md`，內容包含 LINE Bot 技術架構與服務流程（Before/After）自動化對照。

## [2026-07-17] FastAPI、LINE Router 與排程 Worker 重構

### 新增檔案
- 新增 `api/main.py` 作為唯一正式 FastAPI ASGI 入口，統一建立 App、掛載靜態 LIFF 頁面、行政 API Router、LINE Router 與 Worker lifespan。
- 新增 `line/line_bot.py`，承接原 `line/main.py` 的 LINE Webhook、LIFF、帳號綁定、Rich Menu 操作及 BreezySign Webhook 路由。
- 新增 `line/worker.py`，將 LINE 待推播任務執行器從 FastAPI/LINE 路由程式抽離。

### 修改檔案
- 修改 `line/main.py` 為舊匯入相容層；正式啟動不再使用此檔，舊測試仍可匯入 `app` 與 `ensure_order_for_case_no`。
- 修改 `db/schema.sql`：移除重複的 `line_tasks` 建表定義，新增 `scheduled_at DATETIME`，並建立 `(status, scheduled_at, id)` 到期任務複合索引。
- 修改 `line/start_line_bot.py`：開發 FastAPI 啟動入口改為 `api.main:app`。
- 修改 `online.bat`：正式 FastAPI 啟動入口改為 `api.main:app`，並移除正式環境的 `--reload`。
- 修改 `README.md`、`line/LINE_Bot_SOP.md`、`CHANGES_UI_CHANG.md`：更新正式入口、模組責任及 Worker 執行方式。

### 新增／調整功能
- FastAPI Server 與 LINE 功能路由分離；既有外部 API URL 維持不變。
- Worker 改為由 `asyncio.Event` 喚醒，不再每 2 秒固定讀取 DB。
- Webhook、LIFF 綁定、重綁審核與 BreezySign 在任務 transaction commit 後呼叫 `wake_worker()`。
- Worker 每次醒來會執行 `scheduled_at <= NOW()` 的任務，接著查詢最近一筆排程；等待期間若有新任務可提前喚醒並重新計算時間。
- Worker 啟動時會立即掃描 DB；無待處理任務時保留最長 60 秒的容錯檢查。
- LINE HTTP Push 改由背景執行緒執行同步 DB／HTTP 操作，避免阻塞 FastAPI event loop。

### 資料庫與驗證
- 已執行 `scripts/init_db.py`，成功重建開發用 `union_db`，共執行 32 個 schema statement，並預載 2026 年國定假日。
- 已驗證實際 DB 的 `line_tasks` 包含 `scheduled_at`，且存在 `idx_line_tasks_due` 索引。
- 已使用 mock token 建立一筆 2 秒後任務，驗證 Worker 能被喚醒、等待至排程時間、執行並更新為 `sent`；測試任務完成後已刪除。
- FastAPI TestClient 已驗證 `/webhook/line`、`/health` 與 OpenAPI 路由正常。
- 開發假資料已成功產生，客戶 HCM、客戶 BeClass 與服務人員資料已匯入；既有財務匯入流程因 Excel 工作表名稱不符而未完成，需另案修正。
- 完整 pytest 未執行：目前 `.venv` 未安裝 `pytest`；改用 `unittest discover` 時，pytest-based tests 亦因同一相依套件缺失無法載入。

## [2026-07-17] LINE／LIFF 前端可串接 JSON 設定完善

### 設定檔調整
- 移除尚未對外串接的 `config/webhook_replies.json`，改為 `config/message_templates.json`。
- `message_templates.json` 統一管理 Webhook 回覆、一般推播、排程推播與私人客服常用回覆，支援分類、啟用狀態、Text/Flex、變數描述及使用場景。
- 重構 `config/line_menu.json`，支援多組 Menu、尺寸、顏色、按鈕範圍、message／uri／LIFF／postback Action、預設 Menu 與圖片來源設定。
- 重構 `config/liff_settings.json`，新增頁面與動態欄位結構，可定義文字、日期、電話、數字、單選、多選與自訂問題；必要欄位標記為 `system_field`。
- 新增 `config/customer_service.json`，預留私人客服服務時間、狀態、閒置時間及靜態回覆文字。本次未建立客服聊天資料表。

### 後端程式與 API
- 新增 `api/schemas/line_config.py`，為四類 JSON 設定建立 Pydantic 驗證模型與跨欄位規則。
- 新增 `services/json_config_service.py`，集中管理固定白名單設定檔，並以暫存檔加 `os.replace` 原子寫入，避免寫入途中產生半份 JSON。
- 重寫 `api/routes/line_system_config.py`，提供訊息範本、Rich Menu、LIFF 動態欄位及客服靜態設定的 GET／POST／PUT／DELETE API。
- 新增訊息範本 preview API，檢查必要變數並產生預覽文字。
- Rich Menu 改為「儲存設定」與「發布至 LINE」分開；預設 Menu 禁止直接刪除。
- LIFF 系統必要欄位禁止直接刪除，自訂欄位可以新增、修改、排序與刪除。
- 修改 `line/line_bot.py`，改從 `message_templates.json` 讀取已啟用的文字範本。
- 重構 `line/setup_rich_menus.py`，依新 Menu JSON 動態建立 LINE areas/action payload 及產生圖片。

### 文件與圖片儲存決策
- 重寫 `config/README_CONFIG.md`，列出 JSON 欄位、完整 API、前端串接方式與安全注意事項。
- 已確認目前 `db/schema.sql` 沒有圖片、附件或媒體資料表。
- 本次依需求不修改 DB、不新增圖片上傳 API；文件已記錄後續共用 `media_assets` 設計。
- 建議圖片實體存放於 Cloudflare R2／S3／MinIO、NAS 或專用媒體目錄，MySQL 只保存分類、擁有者、storage key、MIME、大小、SHA-256 與 LINE message ID；Rich Menu 圖片及 LINE 用戶照片可用同表分類管理。

### 驗證
- 四份 JSON 均已通過對應 Pydantic Model 驗證。
- FastAPI GET API、訊息範本 preview、範本 CRUD、系統欄位刪除保護與預設 Menu 刪除保護測試通過。
- Rich Menu 設定成功轉換為 LINE Messaging API payload；本次未實際呼叫 LINE 發布 API。
- API 測試建立的臨時訊息範本已於測試結束時刪除，原子寫入產生的暫存檔亦無殘留。

## [2026-07-17] LINE 第四階段：Webhook 安全與任務可靠性

### 新增檔案
- 新增 `line/security.py`：以原始 request body、Channel Secret 與 HMAC-SHA256／Base64 驗證 `X-Line-Signature`。
- 新增 `services/webhook_event_service.py`：保存 Webhook 事件並以 `webhookEventId` 唯一鍵去重。
- 新增 `services/line_task_service.py`：統一建立有排程、payload、來源事件與 idempotency key 的 LINE 任務。
- 新增 `config/message_schedules.json`：定義 Asia/Taipei 時區的新好友 D+1、D+2、D+3 排程。
- 新增 `docs/line_stage4_4_5_report.md`：記錄架構、簽章前後、角色、驗證流程與後續工作。

### 修改檔案
- 修改 `db/schema.sql`：擴充 `line_tasks` 的任務類型、鎖定、重試、錯誤與冪等欄位；新增 `line_webhook_events`、`line_users`、`caregiver_verification_codes`。
- 修改 `line/line_bot.py`：簽章正確後才解析 JSON；事件處理失敗 rollback 並回 500，成功標記 completed；加入 follow／unfollow、三日排程與去重。
- 修改 `line/worker.py`：使用 transaction 與 `FOR UPDATE SKIP LOCKED` 領取任務；加入卡住任務恢復、LINE Retry Key、暫時錯誤指數退避及永久失敗狀態。
- 修改 `config/message_templates.json`：啟用 D+1 並新增 D+2、D+3、月嫂驗證提示與失敗文案。
- 修改 `api/schemas/line_config.py`、`api/routes/line_system_config.py`、`services/json_config_service.py`：新增排程 JSON 驗證與 GET／PUT 前端預留接口。
- 修改 `.env.example`：新增 `INTERNAL_API_KEY` 範例。

### 第四階段功能
- Webhook 無有效 LINE 簽章時回 401，不寫 DB、不建立任務。
- 相同 `webhookEventId` 重送時只處理一次；成功事件留下 completed 收件紀錄。
- 新好友建立歡迎訊息與 D+1～D+3；封鎖時更新 blocked 並取消未送出的 onboarding 任務。
- 排程以 Asia/Taipei 計算，再以 UTC DATETIME 保存，修正主機與 DB 時區差異。
- Worker 由 Webhook commit 後立即喚醒，另保留 60 秒低頻容錯掃描。

## [2026-07-17] LINE 4.5：耗時工作 Worker 化、三角色與月嫂驗證

### 功能調整
- 一般文字的 ChromaDB／RAG 查詢由 Webhook 移至 Worker 的 `rag_reply` 任務。
- LINE Push 與個別 Rich Menu 綁定／解除改由 Worker 執行；Webhook 不再同步呼叫 LINE API。
- 建立 `customer`、`caregiver`、`union_staff` 三種 LINE 角色。
- 修改 `config/line_menu.json`，新增工會人員客服選單，預留客服系統與月嫂驗證管理入口。
- 「我是月嫂」不再直接升級身分；改為密碼學安全隨機六位數驗證碼、10 分鐘期限、最多 5 次嘗試，成功後才切換角色與選單。
- 月嫂驗證碼查詢及角色設定接口必須帶 `X-Internal-API-Key`，避免公開取得驗證碼或任意升級角色。

### 資料庫與驗證
- 已執行 `scripts/init_db.py` 重建開發資料庫，成功執行 35 個 schema statement；本次資料為開發資料。
- Webhook 整合測試通過：無簽章 401、有效簽章、事件去重、follow、D+1～D+3、六位數驗證、角色切換、unfollow 取消排程。
- Worker 測試通過：mock LINE 發送成功轉 `sent`；模擬 HTTP 503 後轉回 `pending`、重試次數加一並建立下次重試時間。
- Python compileall、JSON 與 Pydantic 排程設定驗證通過。
- 所有測試資料均已刪除；本次未建立任何一次性 `.py` 檔案。

## [2026-07-17] 開發終端顯示月嫂驗證碼

- 修改 `line/line_bot.py`：開發環境產生六位數月嫂驗證碼後，在 FastAPI 終端顯示驗證 ID、LINE User ID、驗證碼、有效時間與嘗試限制。
- 修改 `.env.example`：新增 `APP_ENV` 與 `SHOW_CAREGIVER_VERIFICATION_CODE`。
- 只有 `development`、`dev`、`local` 或 `test` 環境且顯示開關啟用時才會輸出；`APP_ENV=production` 時強制不顯示敏感驗證碼。

## [2026-07-17] FastAPI 與 ngrok 共同生命週期監控

- 重構 `line/start_line_bot.py`，持續監控 FastAPI 與 ngrok 兩個程序。
- 任一服務停止時會顯示服務名稱、PID／Exit Code，並自動關閉本次啟動的另一個程序樹。
- ngrok 日誌不再丟棄，改以 `[ngrok]` 前綴顯示，方便辨識驗證、連線與 Tunnel 建立錯誤。
- 啟動器會等待最多 15 秒取得公開 Tunnel；失敗時明確退出，不再留下只有 FastAPI 的假啟動狀態。
- FastAPI 改由目前虛擬環境的 Python 直接啟動 Uvicorn，避免 `uv run` 選到不同 Python 環境。
- Ctrl+C 視為正常停止；Windows 依本次 PID 清理程序樹，不再依程序名稱關閉所有 ngrok。

## [2026-07-17] 4.6 伺服器異常彈窗與互動式重新啟動

- 修改 `line/start_line_bot.py`，新增 `ENABLE_SERVER_FAILURE_POPUP` 環境開關，預設為 `false`，避免開發測試期間持續跳出視窗。
- FastAPI 或 ngrok 異常後先清理兩個服務，再顯示置頂錯誤視窗，內容包含故障服務與 Exit Code。
- 彈窗提供「重新啟動」與「關閉」：重新啟動會由同一個監控程序重建 FastAPI 與 ngrok，不會遞迴產生多個啟動器；關閉則結束監控並等待人工啟動。
- 正常 Ctrl+C 不顯示異常視窗，也不會自動重新啟動。
- Windows 自訂 Tk 視窗無法建立時，會退回內建 Retry／Cancel 錯誤視窗。
- 開發環境未啟用彈窗時，異常會在互動式終端顯示故障原因，並詢問 `是否要重新啟動 ngrok & FastAPI？(y/n)`；輸入 `y` 重啟兩個服務，輸入 `n` 才結束啟動器。
- 非互動式環境沒有可用的標準輸入時不會卡住等待，會記錄原因並安全退出。

## [2026-07-18] 專案文字與終端編碼統一為 UTF-8

- 完整掃描專案文字檔，未發現 Big5／CP950 原始檔；139 個文字檔可正常以 UTF-8 讀取。
- 新增 `.editorconfig`，要求編輯器使用 UTF-8 無 BOM；一般文字檔使用 LF，Windows 批次檔使用 CRLF。
- 新增 `.gitattributes`，統一 Git 文字換行規則並標記常見圖片、Excel、PDF 為 binary。
- 將 `line/line_bot.py` 從 UTF-8 BOM 統一為 UTF-8 無 BOM。
- 將 `line/test_result.txt` 從 UTF-16 LE 轉為 UTF-8 無 BOM，內容保持不變。
- 修復 `document/資料庫、資料處理/資料庫欄位映射與資料字典規格書.md` 中的 Unicode 替代字元損壞內容。
- `start.bat`、`online.bat` 新增 UTF-8 code page、`PYTHONUTF8=1` 與 `PYTHONIOENCODING=utf-8`。
- 啟動器、資料初始化、假資料、匯入與監控腳本同步設定 stdout／stderr 為 UTF-8，降低 Windows CP950 終端造成的執行亂碼。

## [2026-07-18] 工作人員統一待審接口與重新綁定終端審核

- 修改 `line/line_bot.py`，新增 `GET /api/line/staff/review-requests`，統一彙整 `client_rebind` 與 `caregiver_verification` 待處理事項。
- 新增統一 approve／reject API；客戶重新綁定沿用既有核准與拒絕邏輯，月嫂核准時才向工作人員回傳驗證碼，拒絕時取消驗證碼並建立通知任務。
- 既有重新綁定 GET／approve／reject 接口保留相容性，但補上 `X-Internal-API-Key` 驗證。
- 修改 `line/start_line_bot.py`，新增非阻塞重新綁定審核器；不阻塞 FastAPI／LIFF 請求，也能持續監控 ngrok 與 FastAPI。
- 新增 `ENABLE_REBIND_CONSOLE_REVIEW` 開關；開發終端輸入 `y` 呼叫正式核准 API、輸入 `n` 呼叫正式拒絕 API，`APP_ENV=production` 時強制停用。
- 修改 `config/message_templates.json`，新增月嫂驗證申請被拒絕時的通知文字。
- 統一待審 API 權限、月嫂核准／拒絕與終端 y 核准流程測試通過；所有資料庫測試資料均已清除。

## [2026-07-18] 移除舊 FastAPI 相容入口

- 刪除 `line/main.py`；正式且唯一的 FastAPI ASGI 入口統一為 `api.main:app`。
- 修改 `tests/test_case_no_contract.py` 與 `tests/test_payment_routers.py`，改由 `api.main` 匯入 App，LINE 專用函式則由 `line.line_bot` 匯入。
- 修改 `system_map.md`、`system_map.yaml` 與 `CHANGES_UI_CHANG.md`，移除已過時的 `line.main:app` 啟動說明。
- 確認 `line/start_line_bot.py` 已使用 `api.main:app`，並完成 App、LINE 函式匯入及 OpenAPI 路由驗證。
- 專案虛擬環境未安裝 `pytest`，因此本次以直接執行測試函式及 Python 語法編譯作為替代驗證。

## [2026-07-18] Schema 項次與資料字典同步修正

- 修改 `db/schema.sql`：將 `v_order_details` 後方重複的 20～26 項更正為連續的 26～32 項；僅修改註解，沒有變更資料庫結構。
- 修復 `document/資料庫、資料處理/資料庫欄位映射與資料字典規格書.md` 第 46 行附近的 Markdown 表格混接問題。
- 依 Schema 補齊 `clients`、`beclass_records`、`staff` 的現有欄位，移除 BeClass 文件中不存在於 Schema 的 `gender`。
- 資料表總覽擴充為 31 張實體表與 1 個 View，共 32 個資料庫物件。
- 補充月嫂複選、可工作區間、排班、帳務與 LINE 相關資料表用途。
- 修正文件對不存在的 `data_anomaly_events` 隔離表之錯誤描述，明確標示目前應使用既有匯入／爬蟲日誌。
- 驗證結果：Schema 項次 1～32 連續、32 個物件全部有文件紀錄、Markdown 表格欄數一致、UTF-8 無替代字元。

## [2026-07-18] LINE 確認請求統一存入 MySQL

- 修改 `db/schema.sql`：將 `caregiver_verification_codes` 擴充並更名為 `line_confirmation_requests`，統一保存 `caregiver_verification` 與 `client_rebind`。
- 月嫂流程維持原設計：使用者傳送「我是月嫂」時立即產生六位數驗證碼，工作人員由受保護接口查看後決定是否交付，月嫂本人輸入正確才切換角色。
- 修改 `line/line_bot.py`：重新綁定申請不再寫 JSON；改保存客戶 ID、名稱快照、舊／新 LINE User ID 與處理狀態。
- 重新綁定核准／拒絕加入 transaction 與 `FOR UPDATE`；核准後保存 `approved`，拒絕保存 `rejected`，不再刪除已處理紀錄。
- 現有舊版重新綁定 API、統一工作人員待審 API 及 `start_line_bot.py` 呼叫網址保持相容。
- 刪除空的 `config/rebind_requests.json`，並更新設定說明、LINE SOP、第四階段報告及資料字典。
- 執行 `scripts/init_db.py` 成功重建開發 DB，共執行 35 個 Schema statement；客戶、BeClass、月嫂各 50 筆開發資料匯入成功。
- 流程測試通過：重新綁定核准、拒絕、統一待審清單、月嫂驗證碼工作人員查看，以及有效 LINE 簽章下的「我是月嫂」申請、本人輸入驗證碼、角色切換；測試資料已清除。
- 既有財務假資料流程另有不一致：匯入器期待「銀行流水明細」工作表，但生成器輸出「合作社帳戶／資料庫」；第二階段 lifecycle 生成亦回傳空白錯誤。本次未擴大修改財務模組。

## [2026-07-18] LINE 月嫂角色命名統一與人工核准流程

- LINE 月嫂角色由 `caregiver` 統一改為 `staff`，與既有 `staff` 主表、`staff_id`、排班及媒合API命名一致；`union_staff` 保留表示工會人員。
- `line_confirmation_requests.request_type` 由 `caregiver_verification` 改為 `staff_verification`，並移除六位數驗證碼、期限及嘗試次數欄位。
- 使用者輸入「我是月嫂」後只建立待審請求，不再產生或接受驗證碼；工會人員核准後，系統在同一交易內將角色改為 `staff`、完成請求並排入月嫂Rich Menu綁定任務。
- 統一待審API保留給正式Web/UI串接：`GET /api/line/staff/review-requests` 及對應approve／reject接口，持續以 `X-Internal-API-Key` 保護。
- 開發啟動器改為同時顯示月嫂身分與客戶重新綁定待審項目，接受終端 `y/n`；由 `ENABLE_LINE_REVIEW_CONSOLE` 控制，正式環境強制停用。
- 開發環境未設定 `INTERNAL_API_KEY` 時，啟動器會建立只存在本次程序生命週期的隨機內部金鑰，FastAPI子程序共用但不寫入檔案。
- Rich Menu、訊息範本、圖片檔、SOP、設定說明、階段報告及資料字典同步改用 `staff` 命名。
- 已以 `scripts/init_db.py` 重建開發Schema；整合測試通過有效簽章「我是月嫂」→待審→核准→`role=staff`→`status=approved`，測試資料已清除，未建立一次性Python檔案。

## [2026-07-18] 開發人工審核改為一次性通知

- 移除`start_line_bot.py`每3秒呼叫`GET /api/line/staff/review-requests`的固定輪詢。
- 啟動器新增只綁定`127.0.0.1`與隨機Port的臨時通知入口；URL只透過子程序環境變數`DEV_REVIEW_NOTIFY_URL`傳給FastAPI。
- Webhook或LIFF成功提交`staff_verification`／`client_rebind`後，以`X-Internal-API-Key`向本機入口推送一次通知，終端立即顯示`y/n`。
- 啟動器只在每次啟動完成時掃描一次既有待審資料，作為服務中斷期間通知遺失的恢復機制。
- 通知失敗不影響Webhook或LIFF成功回應，確認請求仍保存在MySQL並可由正式Web/UI處理。
- Python語法及單筆通知測試通過：通知佇列只收到一筆`staff_verification`事件，沒有建立一次性Python檔案。

## [2026-07-20] 第五階段5.1：開發啟動器移至專案根目錄

- 將`line/start_line_bot.py`移至專案根目錄並更名為`start_fastapi_ngrok.py`，定位為開發用FastAPI＋ngrok一鍵啟動、程序監控與終端人工審核器。
- 搬移後將`PROJECT_ROOT`改為啟動器所在目錄，確保`.env`、`.venv`、`api.main:app`及設定檔仍從專案根目錄解析。
- `start.bat`更新為呼叫根目錄啟動器，並新增`setlocal`、`cd /d "%~dp0"`及絕對虛擬環境Python路徑，所有初始化、匯入、FastAPI/ngrok及Streamlit均使用同一Python環境。
- 檢查`online.bat`：正式腳本維持直接啟動`api.main:app`，不啟動開發用ngrok；加入提示說明LINE正式公開入口將於5.2改用Cloudflare Tunnel。
- README、LINE階段報告與設定說明同步更新啟動器路徑及開發／正式用途。
## [2026-07-22] 第五階段 5.1：LINE 管理中心安全入口

- 先取得並合併 `upstream/main`；無衝突，保留既有本地 LINE/FastAPI 修改及上游新增功能。
- `db/schema.sql` 新增 `admin_users`、`admin_sessions`、`admin_audit_logs`，並成功執行 `scripts/init_db.py` 套用至開發資料庫。
- 新增 `services/admin_auth_service.py`：scrypt 密碼雜湊、短時效不透明 Session、角色判斷與操作稽核。
- 新增 `api/dependencies/admin_auth.py`、`api/routes/admin_auth.py`、`api/schemas/admin_auth.py`：內部金鑰、登入、登出、目前登入者與 Session 延長接口。
- 新增 `api/routes/line_admin.py`：LINE／Worker／DB 健康狀態與前端能力清單。
- 修改 `api/routes/line_system_config.py`：設定讀取與異動加入角色權限；公開 LIFF 設定讀取維持相容。
- 修改 `api/main.py`：註冊管理路由、限制 CORS 白名單並記錄已驗證的管理異動。
- 新增 `ui/services/line_api_client.py` 與 `ui/pages/07_line_management.py`：Streamlit 伺服器端 API Client、登入頁與 LINE 管理中心分頁骨架。
- 新增永久管理工具 `scripts/create_admin.py`；不建立預設帳密，亦未留下任何一次性 Python 檔案。
- 修改 `start.bat`，使開發用 FastAPI、終端審核器與 Streamlit 共用同一內部金鑰；`online.bat` 正式模式缺少固定金鑰時拒絕啟動。
- 新增 5.1 安全回歸測試，完成 Python 編譯、OpenAPI 路由、未授權拒絕、公開 LIFF 相容與 Schema 初始化驗證。
## [2026-07-22] 第五階段 5.1.1：開發模式略過管理員登入

- 新增 `ENABLE_ADMIN_AUTH` 開關；開發環境設為 `false` 時使用暫時的 `system_admin` 開發身分，不要求輸入帳密。
- `APP_ENV=production` 強制啟用管理員 Session，無法透過開關略過。
- `X-Internal-API-Key` 在開發略過模式仍為必要條件，不會把內部金鑰交給瀏覽器。
- Streamlit LINE 管理中心在略過模式直接進入並顯示醒目警告，不顯示登入／登出控制。
- 稽核紀錄支援沒有 DB 帳號 ID 的開發身分，避免外鍵錯誤。
- 開發 `.env` 已設為 `ENABLE_ADMIN_AUTH=false`；`.env.example` 維持安全預設 `true`。
## [2026-07-22] 第五階段 5.2：訊息管理中心

- `ui/pages/07_line_management.py` 的訊息管理分頁由預留畫面改為實際功能。
- 新增 `ui/components/line_message_manager.py`：搜尋、分類／狀態篩選、新增、修改、複製、預覽、啟停及二次確認刪除。
- 擴充 `ui/services/line_api_client.py`，加入訊息範本 state、CRUD、草稿預覽與 `If-Match` revision。
- `services/json_config_service.py` 新增 SHA-256 設定 revision；寫入仍維持 UTF-8 原子替換。
- `api/routes/line_system_config.py` 加入同程序寫入鎖、版本衝突 409、草稿預覽、排程引用防停用／防刪除。
- 訊息異動稽核增加動作、範本 ID 與非敏感摘要；預覽 POST 不記為資料異動。
- 新增 `tests/test_line_message_management.py`，涵蓋文字、Flex JSON、D+1 引用、state 與舊 revision 拒絕。
- 已驗證 state 200、草稿預覽 200、舊 revision 409、D+1 引用防刪 409；未修改正式範本內容，未建立一次性 Python 檔案。

## [2026-07-22] 第五階段 5.3：排程與 Worker 任務管理

- 新增 `ui/components/line_schedule_manager.py`，完成 D+N 排程編輯、日期預覽、啟停、重新加入重跑與 revision 衝突防護。
- 新增 `ui/components/line_task_manager.py`，完成 Worker 任務統計、篩選、分頁、詳細資料、執行歷史及人工取消／立即執行／失敗重試。
- 新增 `api/routes/line_tasks.py`、`api/schemas/line_tasks.py` 與 `services/line_task_admin_service.py`，以 RBAC、transaction、資料列鎖及狀態檢查保護人工操作；`api/routes/line_admin.py` 能力版本同步更新為 5.3。
- 修改 `api/routes/line_system_config.py` 與 `api/schemas/line_config.py`，加入排程 state、`If-Match` revision、IANA 時區與啟用範本檢查。
- 修改 `line/line_bot.py`，讓 `restart_on_refollow` 實際控制重新加入好友時是否取消並重建尚未發送的 onboarding 任務。
- 修改 `line/worker.py` 與 `db/schema.sql`，新增 `line_task_attempts`，逐次記錄 Worker 執行結果、重試、錯誤與 LINE request ID。
- 任務時間在 UI 統一顯示台北時間，「今日成功」以台北日界計算；DB 持續保存 UTC。
- 前端不加入固定輪詢，只在頁面操作或人工重新整理時讀取；立即執行／重試會主動喚醒 Worker。
- 執行開發 Schema 初始化共 40 個 statement；Python 編譯、OpenAPI、任務狀態轉換、執行歷史、API 權限、排程預覽及無固定輪詢測試均通過，測試資料已清除。
- 同步更新 README、設定說明、階段報告及資料字典；未建立一次性 Python 檔案。

## [2026-07-22] 第五階段 5.4：Rich Menu 管理中心

- `config/line_menu.json` 升級為 version 2，三組 Menu 新增 `audience_role`，統一對應 customer、staff、union_staff。
- 新增 `media_assets` 與 `line_rich_menu_publications`；開發 DB 初始化成功執行 42 個 Schema statement。
- 新增 `services/media_storage_service.py`，安全檢查 JPEG／PNG、尺寸及大小，重新編碼並保存檔案 SHA-256 與 DB 中繼資料。
- 新增 `services/line_rich_menu_service.py`，完成單一選單發布、快照、狀態、重試、舊版保留及角色使用者重新綁定。
- `line/worker.py` 接入發布工作喚醒、到期與 stale recovery；`line/line_bot.py` 優先使用 DB 目前發布 ID。
- Worker 啟動時會把 `rich_menu_ids.json` 既有 ID 一次性登記為目前發布版本，不呼叫 LINE、不重發選單。
- 新增 Rich Menu 圖片／發布 API、revision／If-Match 設定保護、RBAC 與操作稽核；舊發布 URL 保留相容。
- 新增 `ui/components/line_rich_menu_manager.py`，支援草稿編輯、Action、預覽、上傳、發布紀錄及失敗重試，不固定輪詢。
- `line/setup_rich_menus.py` 改成可靠發布服務的 CLI 相容入口，不再由 API 啟動不透明子程序重發全部選單。
- uv.lock 同步新增直接 Pillow／python-multipart 依賴並更新專案版本 metadata。
- 8 項 Rich Menu 測試與 102 條 OpenAPI 路由驗證通過；所有 LINE HTTP 均 Mock，測試 DB 與媒體檔殘留為 0，未建立一次性 Python 檔案。

## [2026-07-22] 第五階段 5.5：LIFF 設定中心

- `config/liff_settings.json` 升級為 version 2，統一管理 gateway、bind、registration 三個 LIFF 頁面、共用主題、入口卡片與動態欄位。
- 新增 `config/liff_settings_history.json` 與 `services/line_liff_config_service.py`，保存最多 20 個修改前快照，提供版本紀錄與人工還原。
- `api/schemas/line_config.py` 加入頁面類型、入口 Action、安全連結／CSS 驗證及系統必要欄位契約。
- `api/routes/line_system_config.py` 新增公開 Runtime、管理 state、驗證、歷史與 rollback API；LIFF 修改加入同程序鎖、revision／`If-Match` 409 防覆蓋及管理稽核。
- 新增 `ui/components/line_liff_manager.py`，完成主題、頁面文字、入口卡片、欄位、自訂選項、手機預覽及版本還原介面；前端不固定輪詢。
- `line/static/gateway.html`、`bind.html`、`register.html` 改為讀取同一 Runtime 設定；登記頁可動態產生自訂問題並保存至既有 `survey_details`。
- 新增 `services/line_liff_identity_service.py`；bind／register 改送 LIFF ID Token，正式環境以 `LINE_LOGIN_CHANNEL_ID` 向 LINE 驗證後取得可信任 User ID，開發模式才允許模擬 ID。
- LIFF 輸出使用 `textContent` 與 DOM 建立節點，避免管理端文字形成儲存型 XSS；主題 CSS 與入口 URL 另有 Schema 白名單驗證。
- 新增 `tests/test_line_liff_management.py`，並將遺漏的 pytest 補為開發依賴；5.1～5.5 完整 LINE 管理回歸共 35 項測試通過。
- 完成 Python 編譯、三頁 JSON Schema、系統欄位保護、正式環境防偽及 108 條 OpenAPI 路由直接驗證。
- 公開 Runtime／管理權限／舊 revision HTTP 整合驗證依序為 200／401／200／409；三個 LIFF 頁面離線 Playwright JavaScript smoke test 全部通過。
- 未建立任何一次性 Python 檔案。

## [2026-07-22] 第五階段 5.6：LINE 人工審查中心

- 新增 `services/line_review_service.py`，統一處理月嫂身分認證及客戶重新綁定的查詢、鎖定、核准、拒絕與 LINE 任務建立。
- 新增具 Session／RBAC 的人工審查 API；`line_agent` 可查看，`line_manager` 可核准或拒絕，拒絕原因必填。
- `line_confirmation_requests` 新增 `reviewed_by_admin_user_id`、`decision_reason` 與管理查詢索引；新增可重跑 migration 並成功初始化開發 DB。
- 重新綁定核准前會再次檢查舊綁定快照、新 LINE 衝突及案件資料；已處理申請不能重複執行。
- 月嫂拒絕狀態由舊版 `cancelled` 統一改為 `rejected`；核准與拒絕結果均以具冪等鍵的 Worker 任務通知使用者。
- 新增 `ui/components/line_review_manager.py`，提供統計、篩選、分頁、詳細資料、二次確認及處理理由；清單遮蔽 LINE ID，且不使用固定輪詢。
- 舊內部審查接口及開發終端一次性 `y/n` 保持相容，改為呼叫相同共用服務。
- 新增客戶重新綁定核准／拒絕訊息範本及 5.6 整合測試；5.1～5.6 LINE 回歸共 43 項通過。
- 未建立任何一次性 Python 檔案。

## [2026-07-24] 修復第五階段啟動器 INTERNAL_API_KEY 載入失敗

- 修正 `start.bat` 在 Windows `cmd` 中無法接收 Python dotenv 輸出的問題；開發啟動時會優先沿用既有環境變數，其次讀取 `.env`，仍無設定時建立本次程序專用的臨時金鑰。
- 同步修正第五階段曾修改的 `online.bat`；正式啟動會優先沿用既有環境變數，其次讀取 `.env`，兩者皆無金鑰時維持拒絕啟動。
- 金鑰內容不會顯示於終端或寫入紀錄；未修改 `.env`、FastAPI、LINE Bot、資料庫及 Streamlit 功能。
- 以不啟動服務的批次測試驗證 dotenv 輸出可成功寫入 Windows 批次環境變數，且未留下測試檔案。

## [2026-07-24] 修復第五階段 Streamlit services 套件撞名

- 將第五階段新增的 `ui/services` 更名為 `ui/api_clients`，避免 Streamlit 將它誤認為專案根目錄的後端 `services` 套件。
- 同步更新 LINE 訊息、排程、任務、Rich Menu、LIFF、人工審查元件與 LINE 管理頁的 API Client 引用。
- 保留根目錄 `services/db_service.py` 及既有 01～05 頁面邏輯不變；修復這些頁面載入時找不到 `db_service` 的問題。
- 更新安全測試的 API Client 檔案路徑，並驗證 Streamlit 路徑順序下 `services` 會解析至根目錄後端套件。

## [2026-07-24] 簡化 LINE 管理中心服務人員介面

- 簡化 `ui/pages/07_line_management.py` 的頁籤、登入身分與系統狀態用語；一般服務人員只看到使用狀態，工程資訊限系統管理員展開查看。
- 簡化訊息內容、自動通知、發送紀錄、LINE 下方選單、LINE 表單與待確認申請頁，隱藏範本 ID、LINE User ID、JSON、版本雜湊、重試次數及其他工程欄位。
- 訊息範本的新識別碼與預覽資料改由系統自動產生；服務人員只需設定名稱、用途、啟用狀態及使用者可見文字。
- Rich Menu、LIFF 等工程名稱改為「LINE 下方選單」與「LINE 服務頁面」，操作按鈕改為查看預覽、儲存修改及套用到 LINE。
- 修正健康狀態 `healthy` 被誤顯示為異常，以及兩頁同名「重新整理」按鈕造成的 Streamlit 元件識別衝突。
- 補上介面防退化測試；LINE 管理相關 43 項測試全數通過，並以實際 Streamlit 頁面完成瀏覽器驗收。
- 未修改後端 API 契約、設定檔格式、資料庫 Schema 或 LINE 發送流程；未建立一次性 Python 檔案。

## [2026-07-25] 補齊 LINE Python 模組檔頭說明

- 依 `ui/pages/order/tab2_assign.py` 的格式，為 FastAPI 主程式、LINE Bot、Worker、LINE API、Schema、服務層與 Streamlit LINE 管理元件補上中文「檔案名稱／功能說明」檔頭。
- 修正 `line/line_bot.py` 原檔頭誤標為 `api/main.py`；只修正註解，不變更主程式與子路由關係。
- 唯讀盤點訂單媒合 LINE 功能：確認粗篩、精篩與履歷小卡目前只有模擬說明及 Postback 分支，尚無可發送的 Flex JSON 或可靠任務串接。
- 發現客戶履歷回覆分支使用 Schema 不存在的 `orders.client_approved` 欄位，列入正式串接前修正項目。
- 32 支目標 Python 檔語法檢查通過；LINE 與訂單媒合相關 48 項測試通過。
- 本次未修改 UI 模擬發送流程、資料庫 Schema 或 LINE 任務格式，未建立一次性 Python 檔案。

## [2026-07-28] 月嫂 LIFF 資料驗證與人工核准綁定

- 使用者傳送「我是月嫂」後，系統建立一次性、具期限的驗證連結並透過 LINE 任務送出；LINE 平台限制為使用者點擊後開啟 LIFF，無法強制彈出頁面。
- 新增月嫂驗證 LIFF 頁面、公開查詢／送出 API 與驗證服務，收集姓名、身分證字號及生日並和既有 `staff` 資料比對。
- 驗證連結只在資料庫保存 SHA-256 雜湊，期限 24 小時且最多嘗試 5 次；送出資料僅額外保存身分證末四碼，不重複保存完整身分證字號。
- 擴充 `line_confirmation_requests`，保存比對狀態、命中的 `staff_id`、送出摘要、驗證期限及嘗試次數，並加入可重複執行的 Schema migration。
- 人工審查中心可查看送出資料與遮蔽後的既有月嫂資料；只有成功比對的申請可核准。
- 核准時在同一資料庫交易中綁定 `staff.line_user_id`、更新 LINE 使用者角色為 `staff`，並建立 Rich Menu 綁定任務；同時防止同一月嫂或 LINE 帳號重複綁定。
- 新增 `LINE_STAFF_VERIFICATION_LIFF_ID` 設定；正式使用須在 LINE Developers 建立相同 LINE Login Channel 下的 LIFF App，Endpoint 指向 `/staff-verification-page`。
- 已將 migration 套用至目前開發資料庫，未清空或重建資料；LINE、LIFF、人工審查、任務與 API 安全共 35 項測試通過。
- 未建立一次性 Python 檔案。

### 共用既有 LIFF Gateway 的 HTTP 400 修復

- 修正未設定月嫂專用 LIFF ID 時，驗證頁直接以未登記的 URL 呼叫 `liff.login()`，導致 LINE 拒絕 redirect URI 並顯示 HTTP 400 的問題。
- 月嫂驗證連結現在優先沿用既有 `LINE_LIFF_ID`，先進入已登記的 Gateway Endpoint 完成登入，再以固定白名單目標導向驗證頁。
- Gateway 同時支援一般 query 與 LINE 傳入的 `liff.state`，完整保留一次性 token；其他舊客綁定、新客登記導頁不變。
- 驗證頁若共用 LIFF 登入狀態失效，會留在頁面顯示重新從聊天室開啟的訊息，不再用不合法的 redirect URI 自動跳轉。
- LIFF、月嫂驗證、人工審查、任務及 API 安全回歸共 38 項通過；未新增 LIFF App、未修改資料庫、未建立一次性 Python 檔案。
- 將 `.env` 與 `.env.example` 的舊名稱 `LINE_LOGIN_ID` 統一為程式實際使用的 `LINE_LOGIN_CHANNEL_ID`，並確認 dotenv 可成功載入；LIFF 與月嫂驗證 16 項測試通過。

## 後續待辦紀錄（尚未執行）

1. ~~完善 LINE 管理中心的「使用狀態」~~：已於 2026-07-29 完成主動監控、細分狀態、Worker 心跳、異常／恢復紀錄及管理中心顯示。
2. 異常警報通知：偵測到異常時，主動傳送訊息給指定工會人員，或傳送至工會人員群組。
3. LINE 群組邀請流程：服務人員建立群組並邀請官方機器人後，由官方機器人將該群組的加入邀請連結傳送給已綁定的指定用戶，避免服務人員只能看到名稱、無法從 LINE User ID 辨識並邀請正確對象。

第 2、3 項目前仍僅記錄需求，尚未擬定方案或修改程式。

## [2026-07-29] LINE 主動式健康監控

- 新增獨立 `line.monitor` 程序，不依賴管理頁載入即可持續檢查 FastAPI、MySQL、Worker、任務隊列、LINE API、公開入口、LIFF、JSON 設定與磁碟空間。
- Worker 每 15 秒更新 `service_heartbeats`；Monitor 超過門檻未收到心跳即可主動判斷 Worker 中斷，而不是只看程序內 Task 旗標。
- 新增 `system_health_status`，並擴充 `system_alerts` 的元件、嚴重度、fingerprint、發生次數與恢復資料；連續失敗及恢復具防抖，避免短暫波動與重複事件。
- DB 故障時以 `.monitor_state/line_health.json` 原子快照保存診斷，管理中心仍能顯示資料庫異常；該目錄已加入 Git ignore。
- 新增受管理員 Session 與內部 API Key 保護的狀態／事件 API，LINE 管理中心顯示正常、注意、異常、未知、維護中、最後檢查時間、回應時間及異常紀錄。
- 開發啟動器與 `online.bat` 已啟動獨立 Monitor；管理頁沒有固定輪詢，手動更新只讀取 Monitor 已保存的結果。
- migration 已套用目前開發 DB，未清空資料；33 項監控與 LINE 核心測試通過。完整套件 808 項通過，另有 4 項未修改的訂單／表單 Streamlit 驗收測試因既有固定 3 秒時限逾時，沒有程式例外。
- 本階段不傳送 LINE 警報；指定工會人員／群組通知保留為下一項任務。未建立一次性 Python 檔案。

## [2026-07-29] 開發服務自動重啟與同層雙向監督

- `start.bat` 直接將 `start_fastapi_ngrok.py` 與 `line.monitor` 啟動為同層獨立程序，不再讓 Monitor 成為服務監督器的子程序。
- `start_fastapi_ngrok.py` 管理 FastAPI、ngrok 與 Streamlit，不再於正常關閉時連帶終止 Monitor。
- 除了檢查子程序是否退出，也會主動檢查 FastAPI `/health`、Streamlit `/_stcore/health`、ngrok HTTPS Tunnel 與 Monitor 快照更新；程序仍在但連續三次無回應會視為卡住。
- 單一服務失敗時只重啟該服務，依 1、3、10 秒間隔最多嘗試三次；恢復後保留其他正常服務。ngrok 網址若變更，會更新本次程序的 `BASE_URL` 並重啟需要重新載入網址的 FastAPI 與 Monitor。
- 三次仍無法恢復時，依 `ENABLE_SERVER_FAILURE_POPUP` 顯示 Windows 彈窗或終端 y/n，之後才安全關閉全部子服務。
- 刪除 `scripts/run_development_supervisor.bat`，避免外層 watchdog、`start.bat` 持續向上套娃。
- 新增 `services/runtime_supervision_service.py`，提供兩程序共用的單例鎖、心跳 PID 解析、命令列核對、安全終止及獨立重啟。
- 開發監督器每 15 秒寫入自身及三項子服務 PID；Monitor 可在監督器失聯時清理舊程序並重啟。反向則由監督器檢查 Monitor 心跳與快照並重啟 Monitor。
- 兩邊正常 Ctrl+C／人工關閉時會留下停機標記，避免另一方把正常停機誤判為故障；再次人工啟動時自動清除。
- 服務中斷、自動重啟與恢復會寫入 `system_alerts`，並顯示於 LINE 管理中心既有的「異常與恢復紀錄」。
- Python 語法檢查及 LINE／監控／啟動相關 60 項回歸測試通過；完整測試為 812 項通過、4 項既有訂單／表單 Streamlit AppTest 因固定 3 秒時限逾時，失敗項目與前次相同。
- Windows 啟動批次檔統一為 UTF-8、CRLF；服務監督改由兩個同層 Python 程序處理，不再使用批次 watchdog。
- 本次未建立一次性 Python 檔案。

## [2026-07-29] 監控功能提交、PR 紀錄清理與檔頭同步

- 已將主動監控與同層雙向恢復建立提交 `c12b036 feat: add active monitoring and mutual service recovery`。
- 比對 `origin/LINE-Bot-Wen` 後，重寫 `history/git_push.md`，移除已存在 origin 的舊版 LINE 管理中心紀錄，只保留尚未推送的月嫂 LIFF 驗證綁定與本次主動監控／雙向恢復。
- 檢查本次提交涉及的 14 支 Python 檔，全部具備檔名與功能說明；同步更新服務監督器、Worker、健康檢查、監控服務、管理中心等已變更職責的檔頭。
- `start.bat`、`online.bat` 與監控 migration 使用各自格式的用途註解；JSON 因格式不允許註解，維持由 `config/README_CONFIG.md` 說明。
- 批次檔維持 UTF-8／CRLF；Python 語法檢查、差異格式檢查及 9 項監控測試通過。
- commit 後的 PR 紀錄與檔頭整理目前保留在工作區，尚未建立第二個提交。

## [2026-08-01] 合併後 DB 結構同步與監控故障可見性修復

- pull／merge 後執行完整測試，發現開發 DB 仍使用舊版 `system_alerts` 服務監控結構，缺少新版 `service_monitor_alerts`，造成 4 項監控測試失敗。
- `services/line_health_checks.py` 新增 `database_schema` 主動檢查，確認業務警示、服務監控、程序心跳及健康狀態表的必要欄位存在，不再只以 `SELECT 1` 判斷 DB 正常。
- `services/line_monitor_service.py` 不再靜默忽略監控狀態寫入／讀取失敗；失敗時保留本機快照、寫入 log，並將整體狀態及 `monitor_persistence_status` 標成異常。
- `api/schemas/line_monitoring.py`、`config/line_monitoring.json` 與 `ui/components/line_health_monitor.py` 同步支援 DB 結構檢查及監控資料保存狀態；事件讀取失敗時不再誤顯示為「沒有異常紀錄」。
- 實際執行 `reset_DB.bat` 的底層重建流程時發現 `95_multi_caregiver_schedule.sql` 錯誤引用 `INFORMATION_SCHEMA.CHECK_CONSTRAINTS.TABLE_NAME`；改為連接 `TABLE_CONSTRAINTS` 取得資料表名稱，修復 DROP 後 migration 中斷問題。
- Schema parts 保留既有 lexical filename order；`104_split_system_and_service_monitor_alerts.sql` 需先於 `97_line_active_monitoring.sql` 執行，未採用會破壞舊 DB 遷移的自然數字排序。
- 本機 `union_db` 已成功重建並匯入固定 v3 fixture；確認 `system_alerts.alert_code`、`service_monitor_alerts.event_type`、`service_heartbeats` 與 `system_health_status` 完整存在。
- 監控／migration／重建目標測試 20 項通過；完整測試 1569 項全部通過，僅剩 6 個既有套件棄用警告。
- 本次未建立或遺留一次性 Python 檔案。

## [2026-08-01] 工會人員 LINE 與後台帳號安全綁定

- 新增「綁定後台帳號」一對一 LINE 指令；若在群組輸入，只提示改用官方帳號私訊，不產生含帳密流程的一次性連結。
- 新增 `line_admin_binding_requests` 專用資料表及可重複執行 migration，原始 Token 僅回傳一次，DB 只保存 SHA-256，效期 15 分鐘且最多驗證 5 次。
- 新增工會人員綁定 LIFF 頁面及公開狀態／完成 API；正式環境使用 LINE ID Token 驗證目前 LINE 使用者，開發模式保留既有測試 user ID 機制。
- 綁定時即時核對現有後台帳號與 scrypt 密碼，不建立後台 Session、不保存密碼，也不變更 `admin_users.role`。
- 成功後以同一 DB 交易更新 `admin_users.linked_line_user_id`、`line_users.role='union_staff'`、綁定請求狀態、稽核紀錄及 Rich Menu 任務。
- 防止後台帳號或 LINE 帳號被重複綁定；既有月嫂 `staff` LINE 身分不允許直接覆蓋；已完成 Token 重送具冪等性且異帳號不能改寫其狀態。
- 擴充 `config/liff_settings.json` 與 LINE 服務頁面管理元件，工會人員綁定頁的標題、說明、欄位名稱與提示文字可由現有管理介面設定。
- 更新 `.env.example` 與 `config/README_CONFIG.md`，說明選填的專用 LIFF ID、共用 Gateway 及公開綁定 API 不可使用內部金鑰的安全邊界。
- 本機開發 `union_db` 已以固定 v3 fixture 完整重建，新 Schema 與 migration 均成功套用。
- 新增綁定整合測試並更新 LIFF 回歸測試；舊版 LIFF 歷史還原時會自動補齊新的必要綁定頁。目標 21 項通過，完整測試 1574 項全部通過，僅有 6 個既有套件棄用警告。
- 本次未建立或遺留一次性 Python 檔案。

## [2026-08-02] 工會人員雙頁 Rich Menu 與 LINE 管理中心串接

- 將工會人員下方選單擴充為「快捷訊息」及「工會後台」兩頁，使用 LINE Rich Menu Alias 原生切頁；兩頁屬於同一發布群組，且只有快捷頁會綁定到工會人員。
- 新增群組發布 API 與可靠發布流程：先建立其他頁面和 Alias，確認同版頁面都成功後才套用入口頁，降低半套選單取代既有選單的風險。
- LINE 管理中心的下方選單頁可編輯切頁動作，發布工會雙頁選單時會一起排入 Worker，不需要服務人員分別操作兩次。
- 訊息內容管理新增「傳給媽媽」、「傳給月嫂」及「群組工具說明」三種工會快捷分類與排序；設定仍保存在 `config/message_templates.json`，不新增另一份範本來源。
- 工會人員在一對一官方帳號點選快捷分類後，Webhook 會驗證 `line_users.role='union_staff'`，再以可靠任務送出 Quick Reply；未綁定身分不可使用。
- Worker 新增 `line_push_messages` 任務，可發送文字與 Quick Reply 等 1～5 個 LINE 訊息物件，沿用既有任務鎖、重試及執行紀錄。
- 新增工會人員 LIFF 手機入口及 Session API，以 LINE ID Token 與 `admin_users.linked_line_user_id` 驗證身分；瀏覽器不持有 `X-Internal-API-Key`。目前完成狀態、訂單、排休、待確認及訊息功能的安全入口與導覽，詳細查詢／異動仍列為後續逐項串接。
- 修正 LIFF 導覽頁使用網址參數組合 HTML 的風險，改以 `textContent` 建立畫面，避免手動竄改網址造成前端注入。
- 更新設定規格、檔案功能說明及 Rich Menu／訊息／LIFF 回歸測試；目標 31 項通過，擴大回歸 65 項通過。另 1 項既有監督器測試因本機保留正常關機標記而顯示 maintenance，與本次功能無關，未刪除使用者的執行狀態檔。
- 本次未修改資料庫 Schema、未重建資料庫，也未建立或遺留一次性 Python 檔案。

## [2026-08-02] 系統異常主動通知至工會人員與群組

- 新增 line_alert_notification_targets 與 line_alert_deliveries，分別保存通知對象及具冪等鍵、LINE Retry Key、狀態與退避重試的可靠派送紀錄。
- Monitor 直接將 service_monitor_alerts 的異常、升級、持續提醒與恢復狀態送至 LINE，不依賴 FastAPI 內 Worker，因此 FastAPI 或 Worker 中斷仍可通知。
- MySQL 故障時改用 .monitor_state 中最近一次通知對象快取直接發送嚴重異常與恢復通知，並保存本機去重狀態避免 15 秒監控週期重複洗訊息。
- Bot 加入群組時提示綁定方式；只有已綁定後台帳號的 line_manager／system_admin 可在群組輸入「綁定異常通知群組」或「解除異常通知群組」。
- 新增受管理員權限保護的異常通知設定、對象、測試與派送紀錄 API，並串入 LINE 管理中心「使用狀態」頁。
- 可設定最低通知等級、恢復通知、持續異常提醒間隔、重試參數及各監控元件開關；一般服務人員介面不要求輸入 groupId 或工程識別碼。
- 修正群組 leave 分支誤引用未定義 user_id 的 Webhook 風險，保留 unfollow 原有的個人 onboarding 任務取消行為。
- 修正監控本機快照 details=null 導致狀態 API 回應驗證 500，並移除 FastAPI 主程式中重複註冊的管理操作稽核 middleware。
- 使用既有 scripts/init_db.py 將 migration 套用開發 DB，沒有清空或重建假資料；DB 結構健康檢查已納入兩張新表。
- 通知與監控整合測試 20 項通過，擴大 LINE／權限／任務／LIFF 回歸 63 項通過；未建立或遺留一次性 Python 檔案。
## [2026-08-02] 工會人員 Rich Menu 改為單頁後台入口

- 移除 `config/line_menu.json` 的「工會人員快捷訊息」頁，保留媽媽、月嫂原有選單及工會人員「後台入口」選單。
- 工會後台選單取消 Rich Menu Alias 雙頁切換，保留系統狀態、訂單查詢、月嫂排休、待確認申請與訊息發送五個入口；訊息發送改為底部全寬按鈕。
- 移除 Webhook 的 `union_staff_quick_category` Postback、Quick Reply 組裝及已無用途的快捷範本載入邏輯。
- LINE 管理中心不再顯示「是否加入工會快捷選單」與排序欄位，訊息範本仍可供常用回覆、主動推播與排程使用。
- 設定格式與說明移除快捷選單專用欄位；Rich Menu 通用群組／Alias 能力仍保留，避免限制未來其他多頁選單。
- 更新 Rich Menu 與訊息管理測試；LINE 選單、訊息、工會帳號綁定及任務管理共 21 項測試通過。
- 未直接呼叫 LINE API 或刪除既有發布紀錄；需由 LINE 管理中心重新套用，才會將線上工會選單更新為單頁後台入口。
- 本次未建立或遺留一次性 Python 檔案。

## [2026-08-04] 訂單 LINE 群組綁定與一次性邀請轉送

- 新增訂單服務群組與預期成員生命週期資料表；`orders.line_group_id` 維持目前有效群組來源並加入唯一限制。
- 已綁定後台帳號且具 `line_agent` 以上權限的工會人員，可在群組輸入「綁定訂單 案件編號」。
- 只有「發送邀請連結 https://line.me/...」完整指令會建立媽媽與月嫂的可靠邀請任務；一般網址不觸發。
- Worker 使用 Flex 卡片發送邀請，沿用任務鎖、冪等、Retry Key 與退避重試；Webhook `memberJoined`／`memberLeft` 更新成員狀態。
- 邀請網址採短期任務保存，送達、取消、永久失敗或 24 小時逾期即遮蔽；Webhook 儲存、終端輸出與管理 API 不回傳明文。
- 新增受管理員權限保護的群組清單、明細與解除綁定 API，並串入 LINE 管理中心及月嫂配對訂單詳情。
- 新增針對邀請命令、網址白名單、Flex 與敏感內容遮蔽的測試；擴大 LINE/API 回歸 57 項、完整測試 1604 項通過。
- 已先備份 `union_db`，再只套用 `107_line_order_groups.sql` 增量 migration；未執行會刪除整個 DB 的 `scripts/init_db.py`，管理員帳號數量維持不變。
- 備份保存在本機 `backups/union_db_before_line_order_groups_20260806.sql`，並將 `backups/` 加入 Git ignore，避免資料庫內容被誤提交。
- 未建立或遺留一次性 Python 檔案。

## [2026-08-06] 合併後 Schema Migration Manifest 與 Preserve 升級整合

- 新增 `scripts/schema_migration_manifest.py`，以單一 manifest 明確定義完整初始化與 preserve-data 候選庫升級順序，不再讓正式流程依賴重複數字前綴或單純字典排序。
- `scripts/init_db.py` 保留通用測試用字典排序能力；正式 `main()` 改用 init manifest，並在缺檔或出現未登記 SQL 時 fail-closed。
- `scripts/migrate_preserved_database_additive_schema.py` 改由 preserve manifest 載入 main 與 LINE additive migrations，將舊版 `system_alerts` 拆分排在服務監控與新版 current projection 前。
- preserve runner 新增 LINE 人工審查、月嫂驗證、服務監控、後台綁定、異常通知與訂單群組的 owned-object 契約；部分結構或舊新警報表同時存在時拒絕自動覆寫。
- `107_line_order_groups.sql` 新增 `orders.line_group_id` 欄位存在性檢查；舊 DB 缺少欄位時先安全新增，再建立唯一索引與群組資料表。
- 新增 `tests/test_schema_migration_manifest.py`，驗證 manifest 完整性、缺檔／未登記檔案、LINE/main 相依順序、舊警報表拆分與群組欄位先後順序。
- Migration 目標測試 53 項及 LINE Schema／監控回歸 33 項通過；完整非真實 MySQL 測試 1780 項通過、2 項因需要 `MYSQL_TEST_CONTAINER` 明確排除。
- 本次未執行 `init_db.py`、未修改現有資料庫，也未建立或遺留一次性 Python 檔案。

## [2026-08-06] 服務運作警報與業務流程警示來源契約

- 新增 `services/alert_source_contract.py`，集中定義 `service_monitor_alerts` 為服務運作監控來源、`system_alerts` 為業務流程警示來源，以及兩者的用途與 LINE 通知資格。
- LINE 異常通知服務加入 fail-closed 驗證，只接受服務監控事件；帶有業務警示 `alert_code` 或缺少必要監控欄位的資料會被拒絕，避免跨來源誤發。
- 監控摘要、監控事件、通知設定與派送紀錄 API 加入明確來源資訊與回應 Schema；舊派送紀錄讀取時相容補上服務監控來源。
- LINE 管理中心「使用狀態」與「異常通知」介面加入來源說明，明確區隔 FastAPI、Worker、DB、LINE API 等服務故障與訂單、帳務、媒合等業務警示。
- 新增靜態邊界與整合測試，確認通知服務不讀取 `system_alerts`、業務警示服務不寫入 LINE 派送表，且錯誤來源無法建立通知 payload。
- 階段 B 目標測試 25 項通過；完整非真實 MySQL 測試 1783 項通過，2 項需 `MYSQL_TEST_CONTAINER` 的真實 MySQL 測試依環境排除。
- Python 編譯及 Git 差異檢查通過；未執行資料庫初始化或 migration、未修改現有資料庫，也未建立或遺留一次性 Python 檔案。

## [2026-08-06] LINE 路由單體拆分與 Worker 責任邊界

- 將 1,420 行的 `line/line_bot.py` 重構為 55 行相容聚合入口，`api.main` 仍只需掛載既有 `line.line_bot:router`。
- 新增 `line/liff_routes.py`、`line/webhook_routes.py`、`line/breezysign_routes.py`，分離 LIFF／身分流程、LINE Platform 事件與 BreezySign 簽約事件。
- 新增 `line/route_support.py`，集中共用環境設定、內部 API 金鑰驗證、開發審核通知與正式案件訂單建立；`ensure_order_for_case_no` 保留舊匯入相容性。
- 確認 LINE Webhook 只驗簽、去重、寫 DB、建立可靠任務並喚醒 Worker；LINE API、Rich Menu API 與 ChromaDB 呼叫仍只在 Worker 執行。
- 拆分前後 31 條路由裝飾器完全一致；FastAPI OpenAPI 可正常建立，8 條必要路徑全部存在，完整 API 共 159 條路徑。
- 新增 `tests/test_line_route_split.py`，並更新異常通知靜態測試的 Webhook 檔案位置；LINE 目標測試 86 項通過。
- 完整非真實 MySQL 測試 1787 項通過，2 項真實 MySQL 測試依環境排除；未執行 DB 初始化或 migration，也未建立或遺留一次性 Python 檔案。

### 2026-08-10
- [修復] LINE Bot Webhook _CUSTOMER_COMMANDS 補上 我要綁定訂單 等 Rich Menu 指令對應，確保能正確觸發客戶資料綁定流程。
- [修復] identity.html Gateway 說明文字邏輯：當顯示前置選擇按鈕時，將說明文案調整為 請選擇您是否已填寫過工會基本資料表單。 避免與下方表單說明混淆；並修正 我還沒填寫 按鈕跳轉路徑為 /register-page 以對應系統原有的 Beclass 表單。
- [恢復] 將誤刪的 `register.html` 從 Git 歷史紀錄（commit: `988b945`）中還原，使未填表單的客戶可順利填寫原生或 BeClass 註冊表單。

## [2026-08-11] LINE 客服與月嫂自助服務 Stage 11

- 依 `20_LINE客服與月嫂自助服務正式規格.md` 建立第一版 canonical Customer Service Domain；
  客服需求與事件具狀態、版本、actor、冪等、audit 與 durable LINE delivery 邊界，管理端
  mutation 不直接呼叫 LINE API。
- 新增「服務說明」canonical handler，支援服務流程、收費與補助、進度查詢、修改資料、
  聯絡工會及其他問題等入口；identity、group、service help、knowledge fallback 維持固定
  分派順序。
- 新增 Customer Service 管理 API、typed schemas、bounded UI API client 與 Streamlit
  「客服入口」，支援摘要、列表、明細、狀態／內部備註更新及可靠 LINE 回覆。
- 新增 verified staff self-service API 與 LIFF 訂單／月班表頁；月嫂只能透過正式 LINE
  binding 查詢自己的有效 assignment 案件及 Scheduling-owned 月曆投影，不新增排班 writer。
- 客戶新登記流程保留 canonical identity `flow_id`，登記完成後才續行同一身分綁定；
  Rich Menu 預設入口與圖面同步為「服務登記／服務說明」及月嫂自助查詢入口。
- 新增 `185_customer_service_runtime.sql`、Stage 11 descriptor／release manifest；release 宣告
  API、LINE Worker、Streamlit 必須同版重啟，schema 只允許 absent／exact，partial／drift
  必須 fail closed。
- 建立 merge 未移植 history，明確保留 query-string userId、LIFF 直接改排班、客服直接
  UPDATE client 等 legacy 行為為禁止或延後項目，不把 merge 現況誤當正式規格。

## [2026-08-11] LINE 身分管理與解除 Stage 12

- 依 `21_LINE身分管理與解除正式規格.md` 以 `line_identity_bindings` 為身分關係 SSOT，
  `clients`、`staff`、`admin_users` 的 LINE 欄位只作 owner projection。
- 新增身分綁定列表／明細、同 subject type replacement preview／apply、解除 preview／apply、
  retry 與人工完成等 typed commands、queries、API、bounded UI client 及管理介面。
- 解除採 durable Rich Menu-first saga：先把 binding 轉為 `revocation_pending` 並建立 outbox；
  Worker 成功套用 canonical default menu 後，才清除 owner projection 並完成 `revoked`，避免
  MySQL 與 LINE provider 被誤當原子交易。
- 新增 read／manage／override 三層 capability，LINE 管理中心加入「身分管理」，並將既有頁籤
  名稱收斂為「Rich Menu」與「LIFF 表單」。
- 新增 fingerprint-gated `upgrade_line_menu_merge_defaults.py`；只在 current revision 等於已知
  merge baseline 時追加 canonical revision，人工 divergent revision 不會被覆蓋。此檔是正式
  可稽核升級工具，不是開發用一次性腳本。
- 新增 `186_line_identity_management.sql`、Stage 12 descriptor／release manifest，保存解除 root、
  provider menu、attempt、error、actor、reason、idempotency 與 correlation 等追蹤事實。

## [2026-08-11] Canonical LIFF 首次登入與 15 分鐘期限修復

- 修正 canonical identity LIFF 使用 additional information 後，新 LINE 帳號首次授權會經過
  primary／secondary redirect，而 `/line-identity/` 原本產生 FastAPI 307 的問題；現在
  `/line-identity` 與 `/line-identity/` 都直接提供同一頁面。
- LIFF 在 `liff.init()` 完成後讀取參數，並可由 `liff.state` 防禦性恢復 `purpose`、`flow_id`
  與 staff target，避免首次授權回跳遺失流程 context。
- 新增 typed `/api/v1/line/identity/flow/validate` 唯讀入口；取得 ID Token 後先驗證 flow 存在、
  purpose、LINE user、狀態及 `expires_at`，有效才顯示表單。過期連結會在開頁當下顯示失效，
  apply 時仍保留第二次 Domain 驗證，不能只靠前端防護。
- 新增首次授權路徑、雙 endpoint path、`liff.state` context、開頁驗證順序、Domain expired
  invariant 與 HTTP 410 翻譯回歸測試。

## [2026-08-11] 驗證、工作區與待完成事項

- 重新執行 Stage 11、Stage 12、LIFF entrypoint、LINE Identity Domain／Subsystem 有限測試：
  `.venv\Scripts\python.exe -m pytest -W error ...` 共 41 項通過。
- 本次盤點未發現開發用臨時 Python、patch、輸出或一次性測試產物；新增 SQL、migration
  manifests、正式規格及 fingerprint-gated upgrade script 均屬 release artifact。
- 尚未執行 Stage 11／12 migration、資料庫切換或 LINE provider mutation，也尚未完成正式
  LINE 雙帳號真機驗收。執行中的 FastAPI 仍未載入新 `/flow/validate` route，重啟前公開與
  本機 process 探測皆為 404；需依 release manifest 同版重啟 API、LINE Worker、Streamlit
  後，再驗收新帳號首次授權、過期連結、跨帳號與一次性使用。
- 所有既有 dirty paths 均保留，未執行 `git add`、commit、push、reset、clean 或 stash。

## [2026-08-11] LINE Rich Menu Legacy 匯入 CI 修復

- 修復 `subsystems/line/rich_menu_publication_workflow.py` 的 flake8 `F821`：Rich Menu
  canonical configuration 遷移至 MySQL 後，worker 啟動時的 legacy ID 匯入仍引用已移除的
  `read_config` 與 `config_revision`。
- 抽出共用 current Rich Menu configuration loader，讓發布預覽與 legacy 匯入都從同一份
  MySQL `LineConfigurationSnapshot` 取得設定與 revision；未恢復舊檔案設定 store 依賴。
- legacy `config/rich_menu_ids.json` 仍只作既有 LINE 平台 ID 的一次性匯入來源；匯入不呼叫
  LINE API、不重新發布選單，既有 current publication、交易 commit／rollback 行為不變。
- 新增實際呼叫 legacy 匯入函式的回歸測試，驗證寫入 publication 的 menu、audience role、
  revision 與 provider Rich Menu ID 均正確取自 canonical snapshot 與 legacy ID mapping。
- `.venv\Scripts\python.exe -m pytest -W error` 執行 Rich Menu snapshot 與 LINE access policy
  測試共 `5 passed`；GitHub Actions fatal flake8 規則 `E9,F63,F7,F82` 在排除 CI 不會存在的
  本機 `.venv` 後為 `0`。
- `git diff --check` 與異動檔 strict UTF-8、無 BOM 驗證通過；未修改 schema、migration、
  正式資料庫、LINE provider 或專案相依檔，也未建立或遺留一次性程式檔案。
## [2026-08-12] LINE 身分解除回復 canonical 用戶選單

- 修復月嫂身分解除後仍讀取 legacy `line_rich_menu_publications`，因而切回「訂單查詢／
  尋找專員」舊版用戶選單的 live-drift；新解除請求改選
  `line_rich_menu_publication_tasks` 最新 published `default_menu`。
- 新增 additive schema part 179（合併前部署 artifact 編號為 168）與 LINE stage 13 release
  manifest／descriptor；新解除 request
  保存 canonical publication FK，stage 12 以前的 legacy request 保持可讀且不回填、不改寫。
- 新增 repository、schema 與 release hash 回歸測試；聚焦測試 13 項、擴大 LINE 回歸 29 項、
  schema loader／bootstrap／release 回歸 8 項通過。
- 以 disposable MySQL 驗證完整 bootstrap、legacy/canonical publication 並存、新 request
  canonical FK 寫入及既有 legacy request 讀取；測試資料庫於驗證後刪除。
- 經使用者授權，在本機 `union_db` 套用 stage 13 前建立全庫備份並實際還原驗證；來源與還原庫
  222 張 base table 的逐表 row count 完全一致，migration 後 3 筆既有解除歷史保持不變。
- 啟動同版 FastAPI、canonical LINE worker 與 Streamlit；API／UI HTTP 200、worker heartbeat
  無錯誤。最新 completed revocation request 3 已重新 link canonical publication 5，LINE provider
  readback 確認實際 Rich Menu 一致。
- 備份僅保存在 Git ignored `scratch/line-identity-stage13-deploy-20260812/`，不得提交或外傳；
  完整驗收見 `2026-08-12_line_identity_canonical_default_menu_repair_receipt.md`。

## [2026-08-12] 合併 upstream/main UI 調整 #42

- 將 upstream/main `cfc3b87401e663e6b5e8bda6cab9a739ae6c2a7f` 合併至本地 `main`；
  非重疊功能完整保留，`README.md` 與本工作紀錄的雙邊新增內容均語意合併。
- upstream 已使用 schema part 168～178 與 Work Package 55～65；本次 LINE 修復功能保留，
  repository artifact 改編號為 schema part 179、Work Package 66，並同步 manifest、descriptor、
  hash、測試、索引與 evidence 歷史說明。
- LINE 身分、canonical menu command、客服與 runtime cutover 聚焦回歸為 `36 passed`；
  migration/bootstrap metadata 群組另有 `22 passed`。
- schema 群組的兩項既知失敗（prefix `101`／`165`／`166`／`167` 重號，以及
  `init_db.main()` 未隔離 pytest argv）可在純 upstream tree 重現，依合併裁決保留雲端版本。
- 完整 pytest 在 collection 階段另發現 upstream 新增 Contract Signing import 所需的
  `infrastructure.archive.contract_documents` 未存在，以及 validation seed 測試仍匯入不存在的
  `_INGESTION_KEY`；這些非本次 LINE write set，未擴張修補。合併版本 FastAPI 因前者暫時無法
  啟動，需另案補齊 upstream 漏檔／測試契約後才能恢復直接測試。
- `git diff --check` 所列 trailing whitespace 均可在純 upstream diff 重現；本次衝突解析檔無
  新增 whitespace 錯誤。`history/git_push.md` 仍由 `.gitignore` 排除，本次未執行 remote push。

## [2026-08-12] 更新 upstream/main 合約封存修復

- 確認 upstream/main `e9de8b7015ab1ef1a77c639e0723e98e32fc2f64` 已補回缺少的
  `infrastructure/archive/contract_documents.py`，解除 `api.main` 載入時的模組阻塞。
- 上游同步將驗證資料種子測試從不存在的 `_INGESTION_KEY` 改為正式
  `_ingestion_key(...)` 契約，原先兩個完整測試收集阻塞均已修復。
- 以 `--no-commit --no-ff` 合併最新 upstream/main，過程沒有衝突；保留本地 LINE 修復與
  Contract Signing router 的既有防護提交，未執行遠端 push。
- 驗證 `api.main` 可成功載入；合約封存與驗證資料集聚焦測試 `13 passed`；完整 pytest
  成功收集 `1902` 項測試。
