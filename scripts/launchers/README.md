# 啟動與本機維運腳本

本目錄是開發者與維運人員可直接執行之 launcher 的 current 入口。管理端固定使用 FastAPI＋React；不存在 Streamlit、ngrok supervisor 或 Cloud Run compat UI launcher。

Windows 日常啟停／更新／搬機改用專案根目錄的 `Windows管理.bat`；人工 Cloudflare 設定及搬機順序見 [Windows 管理說明](WINDOWS-REMOTE.md)。原本開發、NAS、DB 維護入口保留各自用途，勿與管理入口同時啟動同一套服務。

## Current launchers

| 腳本 | 用途 |
|---|---|
| `manage_windows.ps1` | 根目錄「Windows 管理」的唯一操作實作，委派既有 supervisor；支援整組啟停、完整更新、前端更新、狀態、安裝依賴、部署包。 |
| `start_windows_remote.bat` | 舊參數的薄轉接：`--connect`→start、`--update-frontend`→frontend、`--prepare`→prepare、`--dry-run`→check；無參數→start LocalOnly。 |
| `start_local_development.bat` | Windows 本機入口。通過 DB current gate 後，由 `supervise_local_runtime.ps1` 啟動 FastAPI 8000、React/Vite 5173、runtime monitor、durable job worker 與 incident worker。 |
| `start_local_development.sh` | macOS／Linux 本機入口；服務邊界同 Windows。 |
| `start_nas_development.bat`／`.sh` | 使用 `.env` 的 NAS MySQL；拒絕 localhost，委派標準開發入口。 |
| `backup_nas_database.bat` | 手動備份或設定每日 18:00 的 NAS SQL 備份。 |
| `initialize_nas_schema.bat` | NAS 安全升級：先備份，在新庫升級並驗證後切換，不清空原庫。 |
| `restore_nas_database.bat` | 選擇成功備份，復原到新庫、驗證後切換。 |
| `initialize_nas_schema.sh` | 技術人員的空庫 fresh 初始化，與 Windows 日常維護入口分開。 |
| `supervise_local_runtime.ps1` | Windows owned-process supervisor；負責 readiness、存活檢查與 scoped cleanup。 |
| `start_local_development_no_auth.bat`／`.sh` | 只供隔離本機的 `local_bypass` 包裝；委派標準入口，不複製啟動流程。 |
| `configure_local_admin_no_auth.bat`／`.ps1` | 修改本機開發認證設定，不啟動服務。 |
| `update_local_database.bat` | 保留資料的 additive schema update；先執行 dry run。 |
| `reset_DB.bat` | 刪除並重建本機 `union_db`；需要明確確認，屬破壞性操作。 |
| `get_durable_job_worker_task_status.ps1` | 唯讀查詢舊 Windows 排程任務。 |
| `uninstall_durable_job_worker_task.ps1` | 明確移除舊排程任務。 |

## Dry run

所有操作從 repository root 執行：

```powershell
.\scripts\launchers\start_local_development.bat --dry-run
.\scripts\launchers\start_local_development_no_auth.bat --dry-run
.\scripts\launchers\configure_local_admin_no_auth.ps1 -DryRun
.\scripts\launchers\update_local_database.bat --dry-run
.\scripts\launchers\reset_DB.bat --dry-run
.\scripts\launchers\get_durable_job_worker_task_status.ps1 -DryRun
.\scripts\launchers\uninstall_durable_job_worker_task.ps1 -DryRun
```

macOS／Linux：

```bash
./scripts/launchers/start_local_development.sh --dry-run
./scripts/launchers/start_local_development_no_auth.sh --dry-run
```

Dry run 只檢查 current path、interpreter、module、executable 與必要設定；不啟動服務、不寫入資料庫、不修改 `.env`。

## Start and smoke test

```powershell
.\scripts\launchers\start_local_development.bat --smoke-test
.\scripts\launchers\start_local_development.bat
```

```bash
./scripts/launchers/start_local_development.sh
```

Current readiness：

- FastAPI：`http://127.0.0.1:8000/health`
- React：`http://127.0.0.1:5173/admin/`
- React API transport：relative `/api`

Windows 免登入入口不要求主機安裝 Node.js：有 `npm.cmd` 時直接啟動 Vite，
否則沿用 Docker 執行 Vite，再由本機 Python gateway 轉送畫面、API 與熱更新連線。
瀏覽器仍使用 `http://127.0.0.1:5173/admin/`；API、gateway 與 Docker 發布的 port 都只綁定本機。

Smoke test 只建立本次 owned 的 FastAPI＋React process，執行 GET-only readiness 後清理。一般入口才會啟動 monitor 與 workers。

## Database operations

### NAS 正式資料庫：備份、升級、復原

日常可直接雙擊根目錄 **`Windows管理.bat`**，選 **6 備份資料庫、7 安全升級資料庫、8 復原資料庫備份**，不必另外尋找腳本。以下三個獨立入口仍保留相同功能與確認流程。

適用架構：Windows 電腦執行程式，NAS 只跑 Docker MySQL。三個腳本都在正式 Windows 電腦操作，只用 MySQL 連線，不需要 SSH。
**目前開發電腦不會自動啟用或安裝正式排程。**

| 需要做的事 | 雙擊腳本 | 操作方式 |
|---|---|---|
| 保存資料 | `backup_nas_database.bat` | 選「立即備份」或「設定每日備份」。 |
| 更新資料庫 | `initialize_nas_schema.bat` | 已改為安全升級；先停止工會系統，依中文提示確認。沒有清空重建選項。 |
| 從備份復原 | `restore_nas_database.bat` | 先停止工會系統，選備份編號並確認；先建立新庫驗證，保留原庫。 |

每日備份預設 **18:00（Windows 當地時間）**。現場在「稽核與系統 → 資料庫備份」修改時間、查看最近成功備份及失敗提示；第一次按「啟用每日備份」才建立排程。
電腦須開機並登入執行系統的 Windows 帳號；錯過時會在下次登入後補跑。排程只備份，不會自動升級或復原。

備份期間可繼續一般業務操作，但不要變更資料表、執行 migration 或 TRUNCATE。SQL 備份包含資料、view、routine、trigger、event，成功須通過匯出完成、結構穩定及檢查碼驗證。
備份不自動覆蓋、輪替或刪除；請維護人員定期確認成功備份、可用容量及獨立設備副本。備份有完整個資，僅授權人員可存取，不提供網頁下載。

升級會先備份，再在新的資料庫副本執行既有 migration 與資料保留驗證；復原也先匯入新的副本。
通過驗證及原帳號連線測試後，才切換正式電腦 `.env` 的資料庫名稱。**原庫、舊備份及失敗副本都保留。**
完成後重新啟動工會系統，使用原帳號及 MFA 確認登入、資料查詢與操作。切換後已產生新資料時，不能直接切回舊庫而忽略新資料。
失敗時不要清空或重複執行，保留畫面與備份紀錄交給維護人員；備份版本不符會停止切換。

#### 技術人員：正式機的一次設定

1. 準備 MySQL 8 的 `mysql.exe` 與 `mysqldump.exe`，加入正式機 PATH。保留原 `.env`，勿複製開發機設定覆蓋正式環境。
2. 將 `nas_database_maintenance.env.example` 複製到專案根目錄 `.env.nas-maintenance`，填寫固定 NAS 位址／port、獨立 backup-read 與 candidate-write 帳號及備份位置；確認與 runtime `.env` 指向同一目標後，才將 `NAS_MAINTENANCE_ENABLED` 設為 `1`。
3. Backup-read 需能完整讀取目標資料、定義及 routine／trigger／event metadata；candidate-write 需能建立與維護 `lu_nas_*` 副本，以及把原 runtime／backup 帳號既有 schema 層級權限等量授予新副本。工具不修改密碼或原庫權限。角色／細粒度權限不會自動升格，遇到時由原權限維護者處理。
4. `.env.nas-maintenance` 僅限正式執行帳號及管理者讀取。密碼不進參數、Git、畫面或 receipt；含空白或 `#` 時保留 dotenv 引號。TLS 沿用原 `.env` 的 DB_SSL_*，不自動降級。
5. 選擇完整路徑 `NAS_BACKUP_DIR`；工具建立專用 `labor_union_nas` 子目錄、限制其存取。先跑三入口的 `--dry-run`（零連線），再人工做首次備份與隔離復原驗收，最後啟用每日排程。
6. Task Scheduler 工作由正式執行帳號擁有，API 亦須在該 Windows 帳號下執行。修改時間不需要重新輸入密碼。

SQL 不包含 MySQL 帳號／GRANT、照片／附件、Windows 設定與 MFA 加密金鑰；這些須另外安全保存。
若 MySQL／NAS 已無法啟動，先由維護人員恢復 MySQL 8 服務與原帳號，再用復原腳本。
不要把 SQL 備份當成整台 NAS 或整套應用程式的完整災難備份。

首次空庫建置仍由技術人員使用低階 `python -m scripts.initialize_nas_schema --apply`（或 Unix `.sh`）；此路徑拒絕覆蓋非空庫，不是三個日常 Windows 入口的一部分。

Compose 現在只啟動 Redis；所有開發入口直接連線 `.env`／process environment 的 MySQL，
不再啟動或管理 `mysql_db`。既有容器與資料卷保留，請勿使用 `down -v` 或 `--remove-orphans` 清除。

先在 NAS 準備好與目前程式版本一致的 MySQL 測試資料庫及應用程式帳號，再編輯本機 `.env`：

```dotenv
APP_ENV=development
DB_HOST=192.168.1.100
DB_PORT=3306
DB_USER=union_app
DB_PASSWORD="replace_with_nas_test_password"
DB_DATABASE=union_db_test
REDIS_URL=redis://127.0.0.1:6379/0
```

IP、port、帳號及資料庫名稱請依 NAS 設定修改；密碼含 `#` 或空白時請保留引號。
Process environment 的 `DB_*` 優先於 `.env`，readiness 與 API 使用同一組設定。
若原本使用不同的 Redis port，也要同步修改 `REDIS_PORT` 與 `REDIS_URL`。
NAS 防火牆與 MySQL 帳號只開放測試電腦的內網來源，不將 MySQL port 轉發至 Internet。
若 NAS 已配置 mTLS，可沿用既有 `DB_SSL_MODE=verify_identity` 與
`DB_SSL_CA`、`DB_SSL_CERT`、`DB_SSL_KEY`；檔案放本機私有位置。

Windows：

```powershell
.\scripts\launchers\start_nas_development.bat --dry-run
.\scripts\launchers\start_nas_development.bat
```

macOS／Linux：

```bash
bash ./scripts/launchers/start_nas_development.sh --dry-run
bash ./scripts/launchers/start_nas_development.sh
```

`--dry-run` 不連線 NAS。若要只驗證連線與 schema、不啟動任何服務，可執行：

```powershell
$env:APP_ENV = 'development'
$env:RUNTIME_DATABASE_TARGET = 'nas'
.\.venv\Scripts\python.exe -m scripts.check_runtime_database
```

啟動前以唯讀 MySQL session 驗證既有 canonical schema，連線失敗或 schema 非 current 即停止，
不自動建庫、匯入或升級 NAS。既有 `update_local_database`／`reset_DB` 仍限本機資料庫。
正常啟動後會沿用現行授權設定，啟動 API、React、monitor 與背景 workers；
workers 仍可能處理待辦工作及已配置的 LINE 通知，請使用隔離的測試資料與 provider 設定。

保留資料更新：

```powershell
.\scripts\launchers\update_local_database.bat --dry-run
.\scripts\launchers\update_local_database.bat
```

捨棄資料並重建：

```powershell
.\scripts\launchers\reset_DB.bat --dry-run
.\scripts\launchers\reset_DB.bat
```

兩者都不應在 API、React、monitor 或 workers 正在使用目標資料庫時執行。`reset_DB.bat` 不得用於需要保留的資料。
`reset_DB` 在 exact `RESET` 確認後以同一份 compact SQL 重建 371 張表，保留既有 root 帳號、MFA 與復原碼消耗狀態，
清除業務資料、非 root 帳號及 sessions；無確認的預檢／dry-run 不改資料。
本機 disposable 完整初始化預設也載入 compact SQL，且拒絕覆蓋已存在的庫。
`base_only`／`max_schema_part` 是保留資料升級測試與舊版重現的明確 fixture 模式，仍沿用歷史片段。

## Runtime ownership

Windows supervisor 只清理它建立並記錄的 process tree；不得依 port、名稱或全機搜尋終止其他程序。Unix launcher 使用 owned process group 與 trap 執行同等清理。

Worker 與 monitor 透過 Private Operations API 工作，不直接取得資料庫 credential。Production 不接受本機 shared-key 模式；production 部署與 provider 操作另需明確授權。
