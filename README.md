# 新竹市月子照顧服務人員職業工會－LINE 應用與行政流程自動化系統

> 目前版本：**v0.2.2**（2026-08-01）｜ADAD Master System Map：**56.0**

> 更新紀錄固定只保留最近三次版本／功能發布，包含目前版本；更早內容請查閱 Git 歷史與 `document/` 規格文件。

## 2026-08-01 更新（v0.2.2）

本次版本（`main@992a4dd`）完成歷史銀行流水重分類、匯入異常警示，以及保留既有資料的 additive Schema Update 收尾。

- **歷史銀行流水重處理**：正式匯入與既有 batch 重處理共用 canonical 分類、dispatch 與 transaction 邊界；支援先 dry-run、人工核對 `plan_fingerprint`，再決定是否 apply。
- **匯入格式修正**：歷史對帳單限制在契約欄位範圍內解析，正確區分第 10 欄銷帳編號、第 12 欄比對欄位、空白欄與備用姓名欄；姓名只供人工參考，不作為自動入帳依據。
- **可稽核且可重播**：保留 canonical row 與 occurrence cardinality，新增 append-only reclassification run／event；exact replay 不重複建立正式交易，任一步驟失敗全批 rollback。
- **`IMPORT-006` 物化警示**：仍無法分類的流水按 batch 彙總顯示於「異常警示中心 → 資料匯入異常」；一般查詢只讀 current projection，不在每次 API render 重算全部流水。
- **警示中心 UI 修復**：資料匯入、流程與系統、帳務三個頁籤均改走集中 API contract/client；已實際驗證不再顯示 `internal_error: 無法讀取系統警示`。
- **保留資料 Schema Update**：新增 schema parts `104`～`108` 與 preserve-data migration runner，涵蓋訂單 lifecycle history／control facts、服務時間條款、system alert current projection 及 `matching_records.sent_resume_at`。
- **安全切換與回復**：本機候選庫 `union_db_candidate_20260801_v4` 已完成真實 MySQL cutover；原始 `union_db` 保留，回復只能透過 switch receipt 明確切回，不得刪除或重建原始資料庫。

驗證結果：

- Schema／migration 集中測試：`82 passed`
- 真實 MySQL preserve-data cutover：`1 passed`
- FastAPI health、警示 API 與 Streamlit 三個警示頁籤：實際驗收通過

ASUS 目標主機仍須先執行歷史 batch dry-run、核對摘要與 fingerprint，再由人工決定是否 apply；程式已發布不代表目標主機資料已完成重處理。

## 2026-07-31 更新（多月嫂排班 UX）

本次更新完成管理端多月嫂排班、配對與案件人力調整流程，正式 ownership 統一以 `case_staff_assignments` 與 assignment-owned `staff_schedule` 為準。

- **三分頁操作入口**：集中為「服務人員月曆」、「月嫂配對中心」與「案件人力配置」；服務人員月曆不再提供案件指派功能。
- **月曆資訊修正**：顯示目前瀏覽月份，支援上／下月與回到本月；同日多筆案件逐筆呈現，不再以「可接案」覆蓋正式訂單資訊。
- **原配對流程與多人 fallback**：保留原本單月嫂四步配對；只有找不到可完整承接服務期間的單一月嫂時，才顯示 2～4 段多人配對。測試環境暫時保留無寫入的多人介面預覽。
- **案件人力 Preview／Apply**：以 1～4 段編輯完整正式 assignment 計畫，先顯示調整前後、排班移除、時數差額與阻擋原因，再由管理員確認套用。
- **多日期休假、順延與代班**：一次操作共用單一 Preview、fingerprint 與 atomic Apply；任一日期失敗即整批 rollback，不留下部分寫入。
- **服務時數守恆**：每次 Preview 與 Apply 都以最新正式資料重算；所有未取消 assignment 的 `actual_hours` 總和必須精確等於訂單 `service_days × service_hours_per_day`，否則拒絕寫入。
- **薪資與國定假日**：薪資依成功寫入的最新正式排班自動計算，不另設人工薪資確認時間；國定假日預設不產生雙倍薪，個案例外必須由工會人員針對明確排班日人工指定並留下備註。
- **配對與檔期鎖定**：新增逐段檔期查詢、媒合方案與事件、逐位聯繫／意願、共用履歷，以及等待訂金鎖的取得、釋放、取消與轉正式流程。

驗證結果：

- 嚴格 flake8（`E9`、`F63`、`F7`、`F82`）：`0`
- 核心資料安全測試：`618 passed, 1 warning`
- 完整 pytest：`1540 passed, 6 warnings`

既有資料庫升級提醒：

- `online.bat` 不會自動套用資料庫 schema。
- 正式啟動新版前必須先備份資料庫，在維護窗口依序套用 `db/schema_parts/95`、`98`～`103` 的相關更新。
- 執行 `scripts/migrate_assignment_schedule_integrity.py` 時應先使用預設 check 模式，確認既有 assignment ownership、同日重複排班與索引狀態，再視結果使用 `--apply`。

## 2026-07-25 更新（v0.2.1）

本次版本完成管理介面 API 化的安全收尾，並統一沿用 LINE 管理中心既有的正式管理員身分與授權系統。

- **正式管理員認證共用**：Data Browser 與國定假日 GET／POST／DELETE 全部改用 `AdminPrincipal` 與 `require_system_admin`，不再自行維護 `X-Auth-Context`、`ADMIN_AUTH_CONTEXT` 或 `admin_role` 字串判斷。
- **雙層管理 API 防護**：Streamlit 管理頁統一送出伺服器端 `X-Internal-API-Key` 與登入後取得的 `Authorization: Bearer <session>`；缺少設定、Session 失效或角色不足時採 fail-closed。
- **可信稽核身分**：Data Browser PATCH 的 audit actor 與 role 直接取自已驗證的 `AdminPrincipal.username`／`AdminPrincipal.role`，不接受 UI payload 指定，也不再由 username 推測角色。
- **UI → API 串接**：Data Browser、訂單／媒合、訂單編輯與月嫂月曆持續改走 FastAPI；排休 ownership 僅使用 `assignment_id`，正式指派維持 preview → confirm → apply 流程。
- **安全交易邊界**：Data Browser 更新、更新前後快照與 audit insert 共用同一 transaction；非法欄位整批拒絕，audit schema 不在 request runtime 動態建表。
- **ADAD 規格同步**：新增 `AdminAuthService`、`AdminAuthorizationDependency`、`UIAdminApiContext` 節點，更新 Data Browser／Holiday 的 dependency、invariant、verification 與編譯後 YAML IR。

部署或啟動管理介面前至少需要：

```env
INTERNAL_API_KEY=replace-with-a-long-random-secret
APP_ENV=production
ENABLE_ADMIN_AUTH=true
```

正式環境必須先由管理員登入取得 Session。只有 `APP_ENV` 為 `development`、`dev`、`local` 或 `test`，且 `ENABLE_ADMIN_AUTH=false` 時可以略過 Bearer Session；`X-Internal-API-Key` 永遠不能略過。

本次安全整合的針對性驗證為 `22 passed`，涵蓋正式認證核心、Data Browser Router／Service、Holiday Router 與 Streamlit runtime AppTest。對應 commits：`8fa3910`、`bd09413`。

---

本專案旨在為「新竹市月子照顧服務人員職業工會」開發地端運作的 **LINE 客服與行政流程自動化系統**。透過將行政人員手動下載的 Excel 名冊自動化匯入資料庫，並提供 Streamlit 管理後台，未來將延伸串接 LINE Messaging API 實現半自動化客戶配對、合約發送與 RAG 客服問答。

---

## 📂 專案檔案結構與設計緣由

本專案的目錄與檔案結構設計如下：

```text
Lobar_union/
├── .venv/                      # Python 虛擬環境 (Git 已忽略)
├── .agents/                    # ADAD 工作流 / 代理自定義配置目錄
├── db/                         # 資料庫 Schema
│   └── schema.sql              # MySQL 資料庫建表語句（帳務使用 client/staff payments 正規化資料表）
├── document/                   # 專案設計與規格說明文件
│   ├── API/                    # API 整合設計文件
│   ├── line/                   # LINE 平台整合相關說明
│   ├── 地端部屬/               # 地端部署指南與安全架構
│   ├── 管理端UI/               # Streamlit 管理介面原型與規格
│   │   └── 表格需求模板/       # 管理端所需的 Excel 報表設計模板 (帳務.xlsx、所需表格.xlsx、週報.xlsx、服務人員契約.xlsx)
│   └── 資料庫、資料處理/        # 資料庫欄位對應、SSOT 業務規則與 Data Pipeline 設計
├── downloads/                  # 檔案監控下載根目錄 (由 File Watcher 監聽)
│   ├── bank/                   # 存放銀行對帳單 Excel 來源檔
│   ├── client_beclass/         # 存放客戶 BeClass Excel 來源檔
│   ├── hcm/                    # 存放 HCM 月子平台 - 市府 Excel 來源檔
│   └── staff_beclass/          # 存放月嫂 BeClass Excel 來源檔
├── api/                        # 後端 FastAPI RESTful API 服務
│   ├── main.py                 # FastAPI 入口程式
│   ├── routes/                 # API 路由模組（orders、matches、schedule、clients、staff、holidays、finance 等）
│   └── schemas/                # Pydantic 資料驗證 Schema 模型
├── services/                   # 業務邏輯與資料庫存取服務層
│   └── db_service.py           # 核心 DB 服務 (含訂單 CRUD、出勤天數動態精算引擎與 36 欄位 safe_int 防護)
├── ui/                         # Streamlit Web 管理前端專區
│   ├── app.py                  # 側邊欄動態導覽殼層 (AppShellUI)
│   └── pages/                  # 獨立頁面模組專區
│       ├── 01_data_browser.py  # 🗄️ 原始資料庫瀏覽與國定假日管理 (DataBrowserUI)
│       ├── 02_orders.py        # 📊 訂單與帳務管理頁面殼層（五個 Tab 委派至 order/）
│       ├── order/              # 訂單總覽、配對、財務、應付帳款、補助核銷與 editor 子模組
│       ├── 03_calendar.py      # 📅 服務人員行事曆與檔期調控 (CalendarUI - 四色 HTML 月曆與天數精算)
│       ├── 05_form_management.py # 📝 表單管理頁面殼層
│       └── form_management/    # 表單建置、範本庫、契約管理與共用 helper 子模組
├── scripts/                    # 核心 Python 運作與 Pipeline 腳本
│   ├── imports/                # 微匯入 Pipeline 專屬目錄 (Micro-Pipelines)
│   │   ├── import_client_beclass.py # 處理 BeClass 客戶匯入
│   │   ├── import_client_hcm.py     # 處理 HCM 客戶匯入 (初始化訂單為「洽談中」)
│   │   ├── import_finance_excel.py  # 處理銀行對帳流水單
│   │   └── import_staff_beclass.py  # 處理 BeClass 月嫂匯入
│   ├── file_watcher.py         # 地端檔案自動監控服務
│   ├── generate_fake_data.py   # 已凍結的歷史假資料腳本（僅供人工參考，不可執行或匯入）
│   ├── reset_fake_database.py  # 以固定 v3 fixture 安全重建本機 union_db
│   ├── export_db_snapshot_fixture_v2.py # 匯出固定格式資料庫快照
│   ├── import_db_snapshot_fixture_v2.py # 驗證後匯入資料庫快照
│   ├── fix_schedule_conflicts.py # 月嫂檔期衝突檢測與自動修復工具
│   ├── init_db.py              # 資料庫初始化與 Schema 導入
│   └── wait_for_db.py          # 輪詢檢測 MySQL 連線就緒腳本
├── docker-compose.yml          # Docker Compose 配置文件，一鍵啟動 MySQL 8.0 持久化容器
├── main.py                     # 專案主程式入口 (FastAPI 與 Streamlit 同時啟動或導向)
├── online.bat                  # 一鍵啟動生產上線服務 (啟動 Docker, wait_for_db, 啟動 services / watcher)
├── reset_DB.bat                # 僅供開發環境：確認資料庫名稱後套用固定 v3 fixture
├── pyproject.toml              # uv 專案管理配置文件
├── requirements.txt            # 從 pyproject.toml 自動編譯導出的相容性依賴清單
├── system_map.yaml             # ADAD 系統架構 SSOT 記憶與狀態事實來源 (Version 56)
├── system_map.md               # ADAD 系統架構 SSOT 說明文件 (Version 56)
└── uv.lock                     # uv 依賴鎖定檔
```

---

## 🛠️ 開發環境與部署架設指南

本專案保留 `online.bat` 作為正式服務啟動腳本。會重設資料庫並產生假資料的 `start.bat` 已移除；開發與測試環境請改用手動啟動流程。

### 1. 批次檔說明

#### 🌐 `online.bat` (生產上線環境一鍵啟動)
此腳本適合生產環境正式上線使用。執行流程如下：
* 啟動 Docker 中的 MySQL 8.0 容器。
* 等待 MySQL 資料庫連線就緒。
* **⚠️ 安全防護**：**不會**執行資料庫初始化與假資料生成，以確保歷史生產資料的安全。
* 並行啟動 FastAPI 後端、Streamlit 網頁前端、`file_watcher.py` 地端 Excel 檔案自動監控匯入服務，以及互動式 Durable Job Worker 終端機。

正式部署時，Durable Job Worker 必須改由 Windows Task Scheduler 監督，而不是依賴互動式終端機。請以系統管理員 PowerShell 執行：

```powershell
.\scripts\install_durable_job_worker_task.ps1 -StartNow
.\scripts\get_durable_job_worker_task_status.ps1
```

開發階段只需執行 `online.bat`。它會啟動 API、Streamlit、檔案監看與獨立的 Durable Job Worker 終端機；不需要註冊 Windows Task Scheduler。Task Scheduler 僅供正式 24/7 無人值守部署，讓 Windows 開機自動啟動 Worker，並在 Worker 非預期結束時依排程規則重啟。

---

### 2. 啟動方式

#### 批次啟動方式
直接在 Windows 終端機（PowerShell）中執行：
```powershell
# 開發/測試環境啟動
.\start.bat

# 只啟動並監控FastAPI與ngrok（不初始化DB、不啟動UI）
.\.venv\Scripts\python.exe .\start_fastapi_ngrok.py

# 生產/上線環境啟動
.\online.bat
```

`online.bat`不啟動開發用ngrok。正式環境的公開入口已移至第七階段，預定改用 Tailscale Funnel。

### LINE 管理中心（第五階段 5.1）

Streamlit 現在提供「LINE 管理中心」入口。FastAPI 使用兩層驗證：由後端服務持有的
`X-Internal-API-Key`，以及登入後取得的短時效管理員 Session。瀏覽器不會直接取得內部金鑰。

第一次使用前先初始化開發資料庫，再建立一個管理員：

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\create_admin.py --role system_admin
```

`scripts/create_admin.py` 是可重複使用的管理工具，不會建立預設密碼。管理員密碼以 scrypt
雜湊保存，Session 原始值只回傳一次，資料庫僅保存 SHA-256 雜湊。正式啟動前必須在 `.env`
設定固定且足夠長的 `INTERNAL_API_KEY`；`online.bat` 缺少此值會拒絕啟動。

開發期間若不想重複登入，可設定：

```env
APP_ENV=development
ENABLE_ADMIN_AUTH=false
```

此模式只略過帳號 Session，`X-Internal-API-Key` 仍會驗證。`APP_ENV=production` 永遠強制
啟用登入，不受此開關影響。

#### 5.1.1 一鍵本機開發初始化（含金鑰）

不同開發者可各自維護本機 `.env`。若要快速補齊最少三個參數，直接執行：

```powershell
.\bootstrap_admin_dev_env.bat
```

腳本會自動寫入（或更新）：

```env
APP_ENV=development
ENABLE_ADMIN_AUTH=false
INTERNAL_API_KEY=<隨機且本機專用金鑰>
```

完成後再啟動本機服務（例如 `.\start.bat` 或其他本機啟動流程）即可進行不需登入的管理端開發測試。

若要一鍵完成「補齊環境變數 + 啟動 API/UI + watcher」，可直接執行：

```powershell
.\dev_API.bat
```

#### 5.2 訊息管理中心

LINE 管理中心的「訊息管理」已接上 `config/message_templates.json`，支援搜尋、分類／狀態
篩選、新增、修改、複製、文字與 Flex JSON 預覽、啟停及二次確認刪除。管理介面會帶入
設定檔內容 revision，若其他管理員已先修改，後端回傳 409 並要求重新載入，避免覆蓋新版。

啟用中的 D+1～D+3 排程所引用的範本不能停用或刪除；必須先在後續排程管理頁解除引用。
已經建立於 `line_tasks` 的待發送任務保存建立當時的訊息快照，不會因範本文字更新而被改寫。

#### 5.3 排程與 Worker 任務管理

LINE 管理中心的「排程任務」已接上 D+N 排程編輯器及 Worker 任務佇列。排程可設定時區、
D+天數、發送時間、訊息範本、啟停及重新加入好友是否重跑；儲存時使用 revision／`If-Match`
避免多人同時修改互相覆蓋。排程變更只影響之後建立的新任務，既有 `line_tasks` 不回溯更新。

任務管理提供狀態統計、條件篩選、分頁、詳細內容與每次執行歷史。依角色可取消待執行任務、
將待執行任務改成立即執行，或把失敗任務重新排入。所有人工操作均經資料庫狀態鎖與管理稽核；
Worker 仍採 Webhook／管理操作喚醒加低頻容錯掃描，前端不會固定每數秒輪詢。

```text
GET  /api/config/message-schedules/state
PUT  /api/config/message-schedules
GET  /api/v1/line/tasks/summary
GET  /api/v1/line/tasks
GET  /api/v1/line/tasks/{task_id}
POST /api/v1/line/tasks/{task_id}/cancel
POST /api/v1/line/tasks/{task_id}/run-now
POST /api/v1/line/tasks/{task_id}/retry
```

#### 5.4 Rich Menu 管理中心

Rich Menu 分頁已接上三種角色選單，可修改名稱、角色、尺寸、顏色、按鈕範圍及
Message／URI／LIFF／Postback Action，並可產生預覽、上傳圖片、保存草稿及建立發布工作。
草稿使用 revision／`If-Match` 防止多人互相覆蓋；發布與儲存分離，不會因修改設定就直接
更動 LINE 官方帳號。

發布工作保存在 `line_rich_menu_publications`，由既有 Worker 喚醒後執行單一 Menu 建立、
圖片上傳及預設選單設定。成功後，`staff`／`union_staff` 角色會分批建立 `rich_menu_link`
任務切換至新版；失敗保留舊版並提供錯誤與人工重試。圖片本體放在 `MEDIA_STORAGE_ROOT`，
MySQL `media_assets` 只保存中繼資料與 SHA-256，不保存 BLOB。

```text
GET  /api/config/line-menus/state
POST /api/v1/line/rich-menus/preview
POST /api/v1/line/rich-menus/{menu_id}/images
POST /api/v1/line/rich-menus/{menu_id}/publish
GET  /api/v1/line/rich-menus/publications
POST /api/v1/line/rich-menus/publications/{publication_id}/retry
```

#### 5.5 LIFF 設定中心

LINE 管理中心的「LIFF 設定」已接上入口選擇、舊客戶綁定及新客戶登記三個頁面。工會人員
可修改共用主題、頁面文字、入口卡片、欄位順序及自訂問題，並先做手機版預覽。儲存後，
使用者下次載入頁面即套用，不需要像 Rich Menu 一樣另外發布。

後端以 revision／`If-Match` 防止多人覆蓋，並保存最多 20 個修改前快照供人工還原。姓名、
電話、預產期、服務天數及地址等系統欄位不能刪除、停用或改變必要類型；新增問題答案會
寫入既有 `beclass_records.survey_details`。

正式環境必須設定 LIFF 所屬的 LINE Login Channel ID。頁面會送出 `liff.getIDToken()`，
FastAPI 向 LINE 驗證後從 token 取得使用者 ID，不採信瀏覽器自行填入的 ID。開發環境可保留
明確的模擬 ID 降級模式。

```env
LINE_LOGIN_CHANNEL_ID=your_line_login_channel_id_here
LIFF_REQUIRE_ID_TOKEN=true
```

```text
GET  /api/config/liff/runtime?page=registration
GET  /api/config/liff/state
POST /api/config/liff/validate
PUT  /api/config/liff
GET  /api/config/liff/history
POST /api/config/liff/rollback/{revision}
```

#### 5.6 人工審查中心

LINE 管理中心的「人工審查」已接上月嫂身分申請與客戶重新綁定。清單支援類型、狀態、
日期及關鍵字篩選，LINE User ID 在清單中會遮蔽，進入具權限的詳細資料後才顯示完整值。

查看審查資料需要 `line_agent` 以上權限；核准或拒絕需要 `line_manager` 以上權限。拒絕必須
填寫原因。所有決定均保存處理管理員、原因與時間，並寫入 `admin_audit_logs`。核准前會以
資料列鎖重新確認狀態；重新綁定還會檢查舊綁定是否已變更及新 LINE 是否與其他客戶衝突。

```text
GET  /api/v1/line/review-requests/summary
GET  /api/v1/line/review-requests
GET  /api/v1/line/review-requests/{request_id}
POST /api/v1/line/review-requests/{request_id}/approve
POST /api/v1/line/review-requests/{request_id}/reject
```

開發終端的一次性 `y/n` 審查仍保留；舊內部接口改為呼叫同一個交易服務，不會固定輪詢。
管理中心也只在頁面操作或人工重新整理時讀取資料。

#### 手動啟動個別服務
若需單獨除錯，可在啟動 Docker 後手動執行以下指令：
```powershell
# 1. 啟動 Docker 容器
docker-compose up -d

# 2. 啟動 FastAPI 後端
uvicorn api.main:app --reload

# 3. 啟動 Streamlit 管理介面
streamlit run ui/app.py

# 4. 啟動檔案監控
python scripts/file_watcher.py
```

`scripts/init_db.py` 會初始化資料庫，僅能在明確確認目標資料庫後個別執行。請勿執行或匯入 `scripts/generate_fake_data.py`；需要新增測試資料時，優先更新有版本且可驗證的 fixture，或建立用途明確的獨立播種腳本及對應測試。一般開發者不需安裝或操作 ADAD，依標準 Git、Python 與 pytest 流程開發即可。

### 3. 重設本機測試資料庫

固定 v3 fixture 只供本機開發／測試使用，會重建 `union_db`，不可對正式資料庫執行。

```powershell
# 顯示檢查結果，不寫入資料庫
.\.venv\Scripts\python.exe -m scripts.reset_fake_database

# 重建本機 union_db；批次檔會傳入明確的資料庫名稱確認
.\reset_DB.bat
```

重設流程會先驗證 manifest、27 表 allowlist、檔案雜湊與資料內容，再套用 schema 及匯入固定快照；任一步失敗都會停止，不會改用歷史 `generate_fake_data.py`。

---

## 🤝 開發與協作規範

本專案由固定開發人員維護。請團隊成員在進行開發與提交修改前，詳閱 **[🤝 開發與協作規範指南](CONTRIBUTING.md)** 以瞭解分支開發流程與 Pull Request (PR) 規範。
