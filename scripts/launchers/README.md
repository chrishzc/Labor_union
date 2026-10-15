# 啟動與本機維運腳本

本目錄是開發者與維運人員可直接執行之 launcher 的 current 入口。管理端固定使用 FastAPI＋React；不存在 Streamlit、ngrok supervisor 或 Cloud Run compat UI launcher。

## Current launchers

| 腳本 | 用途 |
|---|---|
| `start_local_development.bat` | Windows 本機入口。通過 DB current gate 後，由 `supervise_local_runtime.ps1` 啟動 FastAPI 8000、React/Vite 5173、runtime monitor、durable job worker 與 incident worker。 |
| `start_local_development.sh` | macOS／Linux 本機入口；服務邊界同 Windows。 |
| `start_nas_development.bat`／`.sh` | 使用 `.env` 的 NAS MySQL；拒絕 localhost，委派標準開發入口。 |
| `initialize_nas_schema.bat`／`.sh` | 初始化 NAS 空白 `union_db`；Windows 雙擊可確認初始化，或明確確認後清空測試庫重建。`--apply` 僅限空庫。 |
| `supervise_local_runtime.ps1` | Windows owned-process supervisor；負責 readiness、存活檢查與 scoped cleanup。 |
| `start_local_development_no_auth.bat`／`.sh` | 只供隔離本機的 `local_bypass` 包裝；委派標準入口，不複製啟動流程。 |
| `configure_local_admin_no_auth.bat`／`.ps1` | 修改本機開發認證設定，不啟動服務。 |
| `update_local_database.bat` | 保留資料的 additive schema update；先執行 dry run。 |
| `reset_DB.bat` | 刪除並重建本機 `union_db`；需要明確確認，屬破壞性操作。 |
| `get_durable_job_worker_task_status.ps1` | 唯讀查詢舊 Windows 排程任務。 |
| `uninstall_durable_job_worker_task.ps1` | 明確移除舊排程任務。 |
| `manage_gcp_cloud_run_db_bridge.ps1` | 管理既有受控 DB bridge；不建立 UI 或部署 Streamlit。 |

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

### NAS MySQL 測試

若 NAS 已建立空白 `union_db`，先在專案 `.env` 設定 `APP_ENV=development`、NAS `DB_HOST`、
`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_DATABASE=union_db`。初始化帳號必須能讀取完整 schema metadata，
並具有 canonical DDL／system seed 所需權限（包含 table、index、foreign key、view、trigger 與 routine）；
預設不執行刪庫或建庫；只有下述完整確認的清空測試庫操作會刪庫重建。view 的權限需求見下方。若 MySQL binary logging 的 trigger／function policy 阻擋，請由 NAS 管理員配置權限，
腳本不修改全域設定。執行期間停止其他連線 writer。

```powershell
.\scripts\launchers\initialize_nas_schema.bat --dry-run
.\scripts\launchers\initialize_nas_schema.bat
.\scripts\launchers\initialize_nas_schema.bat --apply
```

Windows 可直接雙擊 `initialize_nas_schema.bat`：先唯讀檢查連線與空庫，通過後輸入 `Y` 並 Enter 初始化，輸入 `N` 取消；
結束時保留結果，按鍵才關閉，不需要另外輸入 `--apply`。預檢失敗就顯示錯誤，不會進入初始化。
macOS／Linux 使用 `bash ./scripts/launchers/initialize_nas_schema.sh`，無參數只做唯讀預檢。
`--dry-run` 只驗設定與正式 schema 雜湊、不連線；明確指定 `--apply` 會再檢查空庫後初始化。
Windows 指定參數執行時不詢問 Y/N，也不等待按鍵，保留原本的命令列用法。
設定直接取自 `.env`，process APP_ENV／DB_* 若有不同值會停止，請先清除 override。
目標不是 `union_db`、指向 localhost 或資料庫不存在都停止。已有物件時預設停止，互動模式提供下述清空選項。
初始化會建立完整結構與正式 artifacts 宣告的必要系統資料，不會匯入業務資料或建立管理員帳號。
NAS 新庫直接使用 `db/fresh_schema/labor_union_fresh_current.sql` 的最終結構，
目前為 371 張表、1 個 view、377 個 trigger、758 條指令，不再重播 1,946 條歷史升級指令。
[逐表退役清單](../../db/schema_assembly/labor_union_fresh_table_retirements_v1.json) 列出 38 張複核表的用途、
規格依據與決策：保留政府付款方主檔，其餘 37 張不建立於新庫；既有資料庫的表與資料保留。
NAS 空庫、本機完整初始化及 `reset_DB` 共用此精簡 profile；明確指定舊版 fixture 的初始化及保留資料升級仍走原 assembly／migration。
SQL 與 manifest 由 `scripts/compact_fresh_schema.py` 從新建的本機測試庫產生，綁定原 assembly、
validation manifest 與退役清單的雜湊；來源改變時會停止並要求重新產生，請勿手改 SQL。
成功必須通過與 NAS 啟動器相同的 current gate，然後才執行 `start_nas_development`。
MySQL DDL 可能已提交；失敗時查看 `scratch/nas_schema_initialization/<run>/journal.jsonl`，
腳本不會自動清空 partial database；只有確認資料可丟棄時，才使用下述清空選項。
錯誤會區分執行 SQL 與最後驗證，列出 phase、完成指令數及安全的 MySQL 數字錯誤碼。
`All schema statements completed, but verification failed` 表示指令已執行完，尚未通過完整結構檢查，不能直接視為成功。
唯讀 schema 查核保留 5 秒連線上限，讀寫等待預設 30 秒；明確較短的 caller budget 仍優先。
不需另跑檢查腳本：同一個初始化入口先檢查 MySQL 8.0.16+、InnoDB、可寫狀態、目前帳號與啟用角色的
必要權限、binary log 的 trigger 限制、本機版本驗證檔案及唯讀 metadata 查詢。
完整預檢通過才詢問 Y/N；按 Y 後重新預檢並再讀空庫條件，通過才建表。預檢不建測試表、不更改 NAS 設定。
目前 final view 使用 OR REPLACE，MySQL 因此要求該 view 的 DROP 權限；一般空庫初始化接受只授權該 view。清空重建另要求整個目標資料庫的 CREATE／DROP 權限。
缺權限、版本不相容、唯讀及 binary log 限制會直接在同一視窗顯示原因。執行中或最終驗證失敗則顯示
phase、完成數及安全原因；保留現場，不清空、不重跑，兩層最終驗證通過才回報成功。
已有物件時仍停止初始化；同一入口會再做唯讀版本查核，直接說明現有結構是否完整或為何無法確認。
「現有結構已通過完整版本查核」表示可直接啟動服務，並不會允許對非空庫重跑初始化。

若 `union_db` 只有可丟棄的測試資料，可在同一個 Windows 視窗選擇清空後重建：

1. 先停止使用該資料庫的服務；雙擊 `initialize_nas_schema.bat`。
2. 出現非空庫診斷後，輸入 `R` 並 Enter；腳本先檢查重建權限等條件，有問題就停止。
3. 核對畫面上的 NAS 位址、port、資料庫及 server，再輸入完整 `RESET union_db` 並 Enter。

這會**刪除並重建整個 `union_db`**，移除所有表、檢視、routine、event 與資料，再建立精簡結構和必要系統資料；無法復原。
輸入 N、空白、錯字或中斷輸入就取消，不修改資料庫。確認後仍會重新預檢；可見其他資料庫有外鍵參照時拒絕清空。
重建保留原本 default charset/collation，不修改帳號或全域設定；失敗顯示階段、原因與 journal，不會自動重試。
命令列 `--apply` 仍只接受空庫；需要相同互動時可明確指定 `--interactive`。

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
