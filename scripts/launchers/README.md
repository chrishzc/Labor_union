# 啟動與本機維運腳本

本目錄是本專案應用程式中，開發者與維運人員可直接執行的 launcher 唯一入口。實際服務 process
module（例如 `scripts/run_service_monitor.py`、`scripts/run_durable_job_worker.py`）仍留在 `scripts/`。
個人安裝工具與其 wrapper 不在本目錄的治理、搬移或退役範圍內，也不是其他開發者的必要依賴。

所有命令都從專案根目錄執行。啟動服務不會自動更新 schema；拉取新版程式後，應先依資料需求選擇
「保留資料更新」或「模板重設」，完成後再啟動服務。

每支現行 launcher 都提供唯讀 dry run。Batch／shell／Python 使用 `--dry-run`，PowerShell 使用
`-DryRun`；只驗證路徑、interpreter、module 與必要 executable，不啟動服務、不讀寫 DB、不修改
`.env`，也不查詢或修改 Windows 排程任務。回傳 `blocked` 表示缺少依賴，不代表已執行任何修復。

## 現行入口

| 腳本 | 狀態 | 用途與安全邊界 |
|---|---|---|
| `start_local_development.bat` | active | Windows 本機開發：啟動 MySQL、API、UI、monitor 與 workers；不套用 schema，禁止作為 production deployment。 |
| `start_local_development.sh` | active | macOS／Unix 的本機開發入口；責任與 Windows 版相同。 |
| `start_local_development_no_auth.bat` | active, local-only | 先停用本機 Admin 認證再啟動全部服務；只供隔離開發機，禁止 shared staging／production。 |
| `configure_local_admin_no_auth.bat`／`.ps1` | active, local-only | 只調整本機 `.env` 的 Admin 開發認證設定，不啟動服務。 |
| `update_local_database.bat` | active | 保留現有資料：備份 source → 建立 candidate → 套用 migration／backfill → 驗證 → 同名替換；失敗保留診斷資料並嘗試 rollback。 |
| `reset_DB.bat` | active, destructive | 不保留現有資料：預檢版本化模板 fixture，要求輸入 `RESET` 後刪除 `union_db`、重建並載入模板測試資料。 |
| `start_fastapi_ngrok.py` | active, development-only | 本機 FastAPI/ngrok supervisor；production 明確禁止 ngrok。 |
| `get_durable_job_worker_task_status.ps1` | recovery-only | 唯讀查詢既有 Windows 排程任務；不安裝、不啟動任務。 |
| `uninstall_durable_job_worker_task.ps1` | recovery-only | 移除過去已安裝的 Durable Job Worker 排程任務，保留 `ShouldProcess` 確認。 |

## 常用流程

保留開發者目前資料並升級 schema：

```powershell
.\scripts\launchers\update_local_database.bat
```

捨棄目前資料、恢復成版本庫提供的模板測試資料：

```powershell
.\scripts\launchers\reset_DB.bat
```

`reset_DB.bat` 需要 `fixtures/db_snapshot_v2/v3/manifest.json` 及其完整 fixture。預檢未通過時不會
刪除資料庫。目前版本庫未提供該模板 fixture，因此 reset 入口會安全停止；fixture 重建是另一個
待核准工作，不得直接復活已退役的舊 v3 snapshot。兩種資料庫流程執行前都必須停止 API、UI、
monitor 與 workers，且只能操作本機 `union_db`，禁止用於 production 或 shared staging。

資料庫完成後啟動 Windows 本機環境：

```powershell
.\scripts\launchers\start_local_development.bat
```

執行全部入口前，可逐支檢查：

```powershell
.\scripts\launchers\start_local_development.bat --dry-run
.\scripts\launchers\start_local_development_no_auth.bat --dry-run
.\scripts\launchers\configure_local_admin_no_auth.bat --dry-run
.\scripts\launchers\configure_local_admin_no_auth.ps1 -DryRun
.\scripts\launchers\update_local_database.bat --dry-run
.\scripts\launchers\reset_DB.bat --dry-run
.\.venv\Scripts\python.exe .\scripts\launchers\start_fastapi_ngrok.py --dry-run
.\scripts\launchers\get_durable_job_worker_task_status.ps1 -DryRun
.\scripts\launchers\uninstall_durable_job_worker_task.ps1 -DryRun
```

macOS／Unix 另執行 `./scripts/launchers/start_local_development.sh --dry-run`。

Windows launcher 只在本機 LINE runtime 設定與 access token 通過唯讀檢查時啟動 LINE worker；未設定
LINE 的開發者會看到 `skipped` 提示，其餘本機服務仍正常啟動。這不會自動切換 runtime mode，也不會
把 placeholder credential 當成有效設定。維護者可用下列受控 smoke 實際啟動並檢查服務；完成或失敗
時只終止本次 smoke 建立的 PID：

```powershell
.\scripts\launchers\start_local_development.bat --smoke-test
```

## 已搬移或退役

| 舊入口 | 裁決 | 現行替代 |
|---|---|---|
| 根目錄 `online.bat`／`online.sh` | 搬移並改成描述責任的名稱 | `start_local_development.bat`／`.sh` |
| 根目錄 `start.bat` | 退役；只是 `online.bat` 的重複轉呼叫 | `start_local_development.bat` |
| 根目錄 `dev_API.bat` | 舊名稱誤導，實際會停用認證並啟動全部服務 | `start_local_development_no_auth.bat` |
| 根目錄 `bootstrap_admin_dev_env.bat` 與 `scripts/bootstrap_admin_dev_env.ps1` | 搬移並改名，凸顯會停用本機認證 | `configure_local_admin_no_auth.bat`／`.ps1` |
| 根目錄 `update_DB.bat` | 搬移並改名 | `update_local_database.bat` |
| 根目錄 `reset_DB.bat` | 搬移；模板重設能力仍為 active | `scripts/launchers/reset_DB.bat` |
| 根目錄 `start_fastapi_ngrok.py` | 搬移，仍限開發用途 | `scripts/launchers/start_fastapi_ngrok.py` |
| `scripts/install_durable_job_worker_task.ps1` | 退役；人工裁決已暫緩主機 supervision | 無；現階段由本機 launcher 互動式啟動 worker，舊任務僅提供查詢／解除安裝。 |

請勿為了相容性重新建立舊根目錄 wrapper；舊路徑會重新造成多入口漂移。需要新增 operator entrypoint
時，先依 Entry Point Governance 補齊 owner、環境、安全門禁、替代與退役策略，再放入本目錄。
