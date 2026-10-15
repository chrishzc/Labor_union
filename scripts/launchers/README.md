# 啟動與本機維運腳本

本目錄是開發者與維運人員可直接執行之 launcher 的 current 入口。管理端固定使用 FastAPI＋React；不存在 Streamlit、ngrok supervisor 或 Cloud Run compat UI launcher。

## Current launchers

| 腳本 | 用途 |
|---|---|
| `start_local_development.bat` | Windows 本機入口。通過 DB current gate 後，由 `supervise_local_runtime.ps1` 啟動 FastAPI 8000、React/Vite 5173、runtime monitor、durable job worker 與 incident worker。 |
| `start_local_development.sh` | macOS／Linux 本機入口；服務邊界同 Windows。 |
| `start_nas_development.bat`／`.sh` | 使用 `.env` 的 NAS MySQL；拒絕 localhost，委派標準開發入口。 |
| `initialize_nas_schema.bat`／`.sh` | 首次初始化 NAS 已存在且空白的 `union_db`；Windows 雙擊預檢後按 Y 才建表，命令列可指定 `--apply`。 |
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
不需要刪庫或建庫權限。若 MySQL binary logging 的 trigger／function policy 阻擋，請由 NAS 管理員配置權限，
腳本不修改全域設定。執行期間停止其他連線 writer。

```powershell
.\scripts\launchers\initialize_nas_schema.bat --dry-run
.\scripts\launchers\initialize_nas_schema.bat
.\scripts\launchers\initialize_nas_schema.bat --apply
```

Windows 可直接雙擊 `initialize_nas_schema.bat`：先唯讀檢查連線與空庫，通過後按 `Y` 初始化，按 `N` 取消；
結束時保留結果，按鍵才關閉，不需要另外輸入 `--apply`。預檢失敗就顯示錯誤，不會進入初始化。
macOS／Linux 使用 `bash ./scripts/launchers/initialize_nas_schema.sh`，無參數只做唯讀預檢。
`--dry-run` 只驗設定與正式 schema 雜湊、不連線；明確指定 `--apply` 會再檢查空庫後初始化。
Windows 指定參數執行時不詢問 Y/N，也不等待按鍵，保留原本的命令列用法。
設定直接取自 `.env`，process APP_ENV／DB_* 若有不同值會停止，請先清除 override。
目標不是 `union_db`、指向 localhost、資料庫不存在或已有 table／view／routine／event 都停止。
初始化會建立完整結構與正式 artifacts 宣告的必要系統資料，不會匯入業務資料或建立管理員帳號。
成功必須通過與 NAS 啟動器相同的 current gate，然後才執行 `start_nas_development`。
MySQL DDL 可能已提交；失敗時查看 `scratch/nas_schema_initialization/<run>/journal.jsonl`，
不要直接重跑或執行 reset。腳本不會自動清空 partial database。

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

## Runtime ownership

Windows supervisor 只清理它建立並記錄的 process tree；不得依 port、名稱或全機搜尋終止其他程序。Unix launcher 使用 owned process group 與 trap 執行同等清理。

Worker 與 monitor 透過 Private Operations API 工作，不直接取得資料庫 credential。Production 不接受本機 shared-key 模式；production 部署與 provider 操作另需明確授權。
