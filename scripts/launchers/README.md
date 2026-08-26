# 啟動與本機維運腳本

本目錄是本專案應用程式中，開發者與維運人員可直接執行的 launcher 唯一入口。實際服務 process
module（例如 `scripts/run_service_monitor.py`、`scripts/run_durable_job_worker.py`）仍留在 `scripts/`。
個人安裝工具與其 wrapper 不在本目錄的治理、搬移或退役範圍內，也不是其他開發者的必要依賴。

Worker 與 Monitor 都是 Private Operations API client，不直接連 MySQL。Windows／Unix 本機 launcher
會在目前 process tree 產生一次性的 `INTERNAL_SERVICE_SHARED_KEY`，API 與各 client 共用，但不寫回
`.env`、log 或 Git。若手動分別啟動服務，必須先在同一 shell 設定至少 32 字元的 key；production
不接受 shared key，須待後續部署工作接上 Google-signed OIDC/IAM 後才可啟用 private endpoints。

所有命令都從專案根目錄執行。目前 Windows／Unix 一般本機 UI 啟動固定使用 API
`127.0.0.1:8000` 與 React/Vite `127.0.0.1:5173`；不再啟動 Streamlit。明確傳入
`--smoke-test` 時同樣只建立這兩個 GET-only 服務。Smoke 不啟動 Docker、monitor、File Watcher、worker、LINE 或 provider，也不切換
navigation；日常檔案匯入由 Web UI 上傳。啟動服務不會自動更新 schema；拉取新版程式後，應先依資料需求選擇
「保留資料更新」或「模板重設」，完成後再啟動服務。

每支現行 launcher 都提供唯讀 dry run。Batch／shell／Python 使用 `--dry-run`，PowerShell 使用
`-DryRun`；只驗證路徑、interpreter、module 與必要 executable，不啟動服務、不讀寫 DB、不修改
`.env`，也不查詢或修改 Windows 排程任務。回傳 `blocked` 表示缺少依賴，不代表已執行任何修復。
DB update preview／dry-run 回傳 `blocked` 時，CLI 與 launcher 同時以非零 exit code 停止，且不顯示
`UPDATE` 確認；只有與 current latest release identity／fingerprint 相符的 qualification receipt 可解鎖。
這裡的 fingerprint 是 selected release 自己的 canonical fingerprint，不是整條 release chain 的 aggregate
fingerprint。Fast additive journal 也固定以 `source_database + release_id` 分鏈，舊 release 的 completed
journal 只供追溯，不得阻擋新 release 或被當成同一條 resume chain。

## 現行入口

| 腳本 | 狀態 | 用途與安全邊界 |
|---|---|---|
| `start_local_development.bat` | active | Windows 一般本機開發入口；啟動 FastAPI、React/Vite 與已配置 workers；`--smoke-test` 只驗證 API＋React 並清理本次 owned process。 |
| `start_local_development.sh` | active | Unix 一般本機開發入口；同樣不啟動 Streamlit，`--smoke-test` 使用 owned process group。 |
| `start_local_development_no_auth.bat` | active, local-only | 先停用本機 Admin 認證再啟動同一 FastAPI＋React 開發入口；只供隔離開發機，禁止 shared staging／production。 |
| `configure_local_admin_no_auth.bat`／`.ps1` | active, local-only | 只調整本機 `.env` 的 Admin 開發認證設定，不啟動服務。 |
| `update_local_database.bat` | active | 預設對 `.env` 指定的本機 development 非系統 DB 執行 qualified schema-only additive fast path；每台機器先建立自己的 release-scoped dump／receipt，不建立 candidate、不 DROP source。保留資料 replacement 必須明確使用 `--strategy replacement --allow-long-run`。 |

若 Docker MySQL 未直接 publish 到 `.env` 的 `DB_PORT`，可先建立只綁定 localhost 的暫時 TCP forward，並以 Python 入口的 `--database-port <forward-port>` 覆寫連線 port。此參數只改變當次連線位置，不改寫 `.env`、credential 或 database identity；MySQL client 仍以 `--mysql-container mysql_db` 在既有容器內執行。
| `reset_DB.bat` | active, destructive | 不保留現有資料：預檢版本化模板 fixture，要求輸入 `RESET` 後刪除 `union_db`、重建並載入模板測試資料。 |
| `start_fastapi_ngrok.py` | active, development-only | 本機 FastAPI/ngrok supervisor；production 明確禁止 ngrok。 |
| `get_durable_job_worker_task_status.ps1` | recovery-only | 唯讀查詢既有 Windows 排程任務；不安裝、不啟動任務。 |
| `uninstall_durable_job_worker_task.ps1` | recovery-only | 移除過去已安裝的 Durable Job Worker 排程任務，保留 `ShouldProcess` 確認。 |
| `setup_gcp_cloud_run_compat.ps1` | active, development-only | **開發用 GCE＋IAP 反向 SSH Tunnel 版，嚴禁正式部署使用。** 首次建立或續跑隔離 GCP compat Project，並把 Cloud Run 測試 API 暫時連到本機 Docker MySQL。 |
| `publish_gcp_cloud_run_compat.ps1` | active, staging-only | 在既有 `environment=staging|test`、`deployment=compat` Project中選倉庫及複選本機images，建立不可變tag、push、解析digest，並按API／UI／runtime-ops角色建立或更新compat Cloud Run資源。 |
| `manage_gcp_cloud_run_db_bridge.ps1` | active, development-only | 啟動／停止／查詢 localhost-only Docker TCP forward 與 GCE IAP reverse SSH Tunnel；只允許 compat Project，嚴禁作為正式 DB 路徑。 |

## 常用流程

保留 `.env` 指定之本機資料庫的目前資料並升級 schema：

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
monitor 與 workers；保留資料更新只接受 `.env` 指定的本機 development 非 MySQL 系統 DB，不以
固定資料庫名稱判斷環境，模板重設仍只操作 `union_db`。

Phase 5B controlled foundation：

```powershell
.\scripts\launchers\start_local_development.bat --dry-run
.\scripts\launchers\start_local_development.bat --smoke-test
```

一般互動本機環境使用：

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

## Cloud Run compat staging（開發用 GCE＋IAP 反向 SSH Tunnel 版）

> **嚴禁正式部署使用。** 此版本只為提早驗證 Cloud Run、容器、服務間 OIDC 與目前本機開發 DB
> 的相容性；不具 HA、SLA、固定地端入口、正式資料保護或 production cutover 能力。正式環境仍必須
> 使用核准的 Cloud VPN → 地端 NAS／MySQL 路徑。

以下入口只執行 `Cloud_Run_現況相容性部署測試封裝計畫.md` 的隔離開發測試拓樸。三支腳本都要求
專案標籤為 `environment=staging|test` 與 `deployment=compat`，拒絕其他 Project；image alias、Cloud
Run資源及tag也固定包含 `compat`。請使用 PowerShell 7（`pwsh`），首次建立環境前先執行dry run：

```powershell
.\scripts\launchers\setup_gcp_cloud_run_compat.ps1 -PreflightOnly
.\scripts\launchers\setup_gcp_cloud_run_compat.ps1 -DryRun
.\scripts\launchers\setup_gcp_cloud_run_compat.ps1
```

`-PreflightOnly`會一次檢查PowerShell 7、Git、Docker CLI／daemon、gcloud、Windows OpenSSH、
`ssh-keygen`、`icacls`、`.env`及三份Dockerfile；只要缺少任何項目，就以編號列出原因與處置方向，
不登入、不build、不建立GCP資源。首次正式執行在任何GCP mutation前，會自動從目前source建置
API、UI、runtime-ops三個images並完成本機container驗收；組員不需要先手動建立或挑選images。

首次入口會以 strict UTF-8 讀取 Git-ignored `.env`，只把必要的 DB、TOTP 與 LINE secret 透過 stdin
建立為 Secret Manager version；不把 `.env`、secret值或 service-account key 放入 image／Git／CLI
參數。它會列出目前帳號可用的Billing Accounts，並從Cloud Billing API的`currencyCode`自動判斷
計費幣別；預算只需輸入數字，腳本會附加例如`TWD`或`USD`。若API因權限或舊版CLI無法回傳幣別，
才會要求人工輸入3碼ISO 4217代碼。若選擇建立新帳務，腳本只會開啟Google Cloud
Billing網頁並等待使用者完成付款與法律資料，無法也不會代替使用者裁決。Project、月預算、subnet
CIDR、Artifact Registry及所有預計建立的付費資源都會在mutation前再次顯示；輸入指定確認字串後
才會繼續。

環境已由首次入口建立後，使用下列入口發布新images：

```powershell
.\scripts\launchers\publish_gcp_cloud_run_compat.ps1 -PreflightOnly
.\scripts\launchers\publish_gcp_cloud_run_compat.ps1 -DryRun
.\scripts\launchers\publish_gcp_cloud_run_compat.ps1
# 只更新指定角色
.\scripts\launchers\publish_gcp_cloud_run_compat.ps1 -Roles api,ui
# 進階模式：改為人工挑選已存在的本機images
.\scripts\launchers\publish_gcp_cloud_run_compat.ps1 -SelectExistingImages
```

發布入口預設從三份Dockerfile重建、完成與首次入口相同的本機驗收，再自動建立唯一immutable tag；
`-Roles`可限制只更新指定角色。只有明確指定`-SelectExistingImages`時才列出本機images供人工複選。
push後一定解析為`image@sha256:<digest>`才允許部署；既有Cloud Run資源只更新image，不清除env、
secret、network或identity設定。gcloud的HTTP 429／`RESOURCE_EXHAUSTED`／rate limit與已知API
propagation錯誤，以及Docker push短暫server error，會採有上限的exponential backoff重試；永久權限、
設定或驗收錯誤仍立即fail closed。

compat拓樸為兩個Services、三個獨立Worker Pools及一個Monitor Job。首次入口另外建立無外部 IP 的
小型 GCE bridge VM、IAP SSH 防火牆規則及 Cloud Run subnet → bridge TCP/13306 規則。本機另啟動
只綁 `127.0.0.1:13307` 的 Docker TCP forward，再由 IAP SSH 建立
`GCE:13306 → 本機:13307 → mysql_db:3306` 反向 Tunnel；MySQL 不直接公開到 Internet。UI公開 URL
仍由 application login＋TOTP保護，UI → API與runtime → API使用Google OIDC。腳本不建立Cloud VPN、
Load Balancer／Cloud Armor、staging NAS、LINE測試channel或production migration，也不建立
service-account JSON key。

bridge manager會在`scratch/cloud-run-db-bridge/<project-id>/`建立該Project專用Ed25519 key，使用
`icacls`移除繼承權限、只保留目前Windows使用者與SYSTEM，再透過OS Login登錄public key；不再要求
新電腦事先存在`~/.ssh/google_compute_engine`。私鑰、known-hosts、PID與log全部維持Git ignored，
不得搬入`.env`、image或版本庫。

```powershell
pwsh -NoProfile -File .\scripts\launchers\manage_gcp_cloud_run_db_bridge.ps1 -Action status -ProjectId <PROJECT_ID>
pwsh -NoProfile -File .\scripts\launchers\manage_gcp_cloud_run_db_bridge.ps1 -Action stop -ProjectId <PROJECT_ID>
pwsh -NoProfile -File .\scripts\launchers\manage_gcp_cloud_run_db_bridge.ps1 -Action start -ProjectId <PROJECT_ID>
```

電腦休眠、斷網、停止 bridge process或停止本機 Docker/MySQL後，Cloud Run DB操作會 fail closed；
不會自動改走公開 DB。實際建立GCP資源會產生費用；測試完成後先停止 bridge，再由操作人員依
測試報告及清理receipt刪除compat資源。首次腳本輸出的Webhook與LIFF URL仍須到LINE Developers
Console人工設定並驗證，這是整體驗收的人工 gate。

Windows／Unix launcher 都先通過 current schema readiness，並只在本機 LINE runtime 設定與 access
token 通過唯讀檢查時啟動 LINE worker；未設定
LINE 的開發者會看到 `skipped` 提示，其餘本機服務仍正常啟動。這不會自動切換 runtime mode，也不會
把 placeholder credential 當成有效設定。Knowledge worker 也只在對應 runtime flag 明確啟用時啟動。
維護者可用下列受控 smoke 實際啟動並檢查服務；完成或失敗
時只終止本次 smoke 建立的 PID：

Smoke 固定 GET-only；不使用既有 DB mutation，不啟動 Streamlit、monitor／worker／LINE／provider。React ready 必須是
5173 `/admin/` 回傳 HTML 且含 `id="root"`，並以 `/api/...` relative proxy 觀察 backend response。每次 run 使用唯一
`scratch/phase5b-dual-run/<run-id>/`，完成或失敗只終止本次建立的 PID tree／process group。

## 已搬移或退役

| 舊入口 | 裁決 | 現行替代 |
|---|---|---|
| 根目錄 `online.bat`／`online.sh` | 搬移並改成描述責任的名稱 | `start_local_development.bat`／`.sh` |
| 根目錄 `start.bat` | 退役；只是 `online.bat` 的重複轉呼叫 | `start_local_development.bat` |
| 根目錄 `dev_API.bat` | 舊名稱誤導，實際會停用認證並啟動受控三服務 | `start_local_development_no_auth.bat` |
| 根目錄 `bootstrap_admin_dev_env.bat` 與 `scripts/bootstrap_admin_dev_env.ps1` | 搬移並改名，凸顯會停用本機認證 | `configure_local_admin_no_auth.bat`／`.ps1` |
| 根目錄 `update_DB.bat` | 搬移並改名 | `update_local_database.bat` |
| 根目錄 `reset_DB.bat` | 搬移；模板重設能力仍為 active | `scripts/launchers/reset_DB.bat` |
| 根目錄 `start_fastapi_ngrok.py` | 搬移，仍限開發用途 | `scripts/launchers/start_fastapi_ngrok.py` |
| `scripts/install_durable_job_worker_task.ps1` | 退役；人工裁決已暫緩主機 supervision | 無；現階段由本機 launcher 互動式啟動 worker，舊任務僅提供查詢／解除安裝。 |

請勿為了相容性重新建立舊根目錄 wrapper；舊路徑會重新造成多入口漂移。需要新增 operator entrypoint
時，先依 Entry Point Governance 補齊 owner、環境、安全門禁、替代與退役策略，再放入本目錄。
