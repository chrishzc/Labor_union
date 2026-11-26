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
| `backup_nas_database.bat` | 手動備份或設定每日 18:00 的 NAS SQL 備份。 |
| `initialize_nas_schema.bat` | NAS 安全升級：先備份，在新庫升級並驗證後切換，不清空原庫。 |
| `restore_nas_database.bat` | 選擇成功備份，驗證後復原至原本庫名，完成後清除本次暫存資料。 |
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

## 首次建帳出現 TOTP 加密設定缺失或無效

先停止網站，再雙擊 `scripts\launchers\configure_initial_totp_key.bat`。
依畫面輸入 `INITIALIZE TOTP union_db`（若為測試庫，以畫面指定名稱為準）。
顯示 `passed` 後完整重啟網站，即可建立 root、掃描 QR Code、驗證綁定、保存復原碼，再返回登入。

工具將隨機金鑰保存於本機 `.env`，不顯示金鑰，也不寫入 MySQL。
有效金鑰會原樣保留；僅本機資料庫且帳號、TOTP、session 及 challenge 資料全空時，才允許建立金鑰。
若已有帳號或驗證資料，會拒絕替換，應恢復原金鑰。請妥善保管 `.env`，不要貼出或提交 Git。
預覽可執行 `python -m scripts.configure_initial_totp_key`，不加 `--apply` 不會寫檔。

## 重置錯誤建立、尚未完成 TOTP 的初始 root

先停止網站服務，再雙擊 `scripts\launchers\reset_incomplete_root.bat`。
工具會顯示本機資料庫、root id 與版本；只有輸入畫面指定的完整確認文字才會清除該初始帳號。
完成後重新啟動網站，即可重新設定帳號密碼，並依「建立 root → QR Code → TOTP 驗證 → 保存復原碼 → 返回登入」完成設定。

僅允許本機資料庫，且帳號安全版本必須仍為初始值 `1`。曾更換帳密／安全設定、已綁定／使用過 TOTP、登入過、已有其他管理員或業務資料引用時拒絕重置。
業務資料、稽核紀錄及加密金鑰保留；不需提供舊帳密。取消不會異動資料。
只想先檢查時，執行 `python -m scripts.reset_incomplete_root_setup`；加上 `--apply` 才會進入確認操作。

## Database operations

<a id="nas-正式資料庫備份升級復原"></a>
<a id="windows-database-maintenance"></a>

### Windows 資料庫維護：備份、升級、復原

日常可直接雙擊根目錄 **`Windows管理.bat`**，選 **6 備份資料庫、7 安全升級資料庫、8 復原資料庫備份**，不必另外尋找腳本。以下三個獨立入口仍保留相同功能與確認流程。

正式部署由同一台 Windows 主機執行應用與本機 Docker MySQL／Redis。三個維護入口依指定 `.env` 連線，不使用 SSH；腳本名稱中的 `nas` 為相容名稱。設定以[正式維護規格 §5](../../.arch-map/requirements/10A_NAS_Fresh初始化與維護復原規格.md#windows-nas-maintenance)為準。
**目前開發電腦不會自動啟用或安裝正式排程。**

| 需要做的事 | 雙擊腳本 | 操作方式 |
|---|---|---|
| 保存資料 | `backup_nas_database.bat` | 選「立即備份」或「設定每日備份」。 |
| 更新資料庫 | `initialize_nas_schema.bat` | 已改為安全升級；先停止工會系統，依中文提示確認。沒有清空重建選項。 |
| 從備份復原 | `restore_nas_database.bat` | 先停止工會系統並選擇備份；依同名復原流程驗證、替換及清理。 |

每日備份預設 **18:00（Windows 當地時間）**。現場在「稽核與系統 → 資料庫備份」修改時間、查看最近成功備份及失敗提示；第一次按「啟用每日備份」才建立排程。
電腦須開機並登入執行系統的 Windows 帳號；錯過時會在下次登入後補跑。排程只備份，不會自動升級或復原。

備份期間可繼續一般業務操作，但不要變更資料表、執行 migration 或 TRUNCATE。SQL 備份包含資料、view、routine、trigger、event，成功須通過匯出完成、結構穩定及檢查碼驗證。
備份位置可用本機、映射磁碟或 UNC 路徑。依序採用 `.env` 的 `NAS_BACKUP_DIR`、選填維護設定檔的同名設定、`CONTROLLED_FILE_STORAGE_ROOT/05_資料庫冷備份 (db_backups)`，最後才用專案下的 `backups/05_資料庫冷備份 (db_backups)`。寫入前須通過存取檢查，不得越界或經 symlink／junction；`--dry-run` 不連線、不寫入。已指定而無法使用的位置不能當成備份成功。新版驗證完成後按臺灣時間月份發布單一 ZIP：

```text
05_資料庫冷備份 (db_backups)/
  2026-10/
    union_db_20261030_180000.zip
```

每日備份是不停機的 SQL 一致性快照。ZIP 內含 `.sql.gz`、`.sha256` 校驗檔與成功紀錄 `.json`；`_partial/` 保存未完成材料，`_maintenance/` 保存適用的升級紀錄。舊備份仍按原格式查核，不須重包；匯入時串流解壓。
復原可由預設備份區或 Windows 選檔窗選取已驗證的 ZIP；舊 `.sql.gz` 須保留完整同名 `.sha256` 和對應 `_receipts/` 成功紀錄。選檔等待操作人員，不設 30 秒時限；取消不連線或修改資料庫。技術人員也可用 `--backup-file` 指定來源。手動來源唯讀、不搬移、不改 `.env`。同名復原不在備份區寫入跨次紀錄。損壞、不完整或經 symlink／junction 的來源不匯入；詳細前提見下方同名復原流程。
一般手動備份不由復原流程覆蓋或刪除；請維護人員定期確認成功備份、可用容量及獨立設備副本。備份有完整個資，僅授權人員可存取，不提供網頁下載。

合約、模板及其他業務附件的根目錄另依[受控檔案正式規格 §8.2](../../.arch-map/requirements/30_Controlled_File_Storage_NAS正式規格.md)；上方 SQL 備份的專案路徑預設不適用於業務附件。部署切換不自動搬移既有附件。
首次寫入會自動建立規格的 01～05 與 `_staging`；案件／日期／月嫂子目錄在新檔確認後依資料建立。上傳與產生的選單底圖都在 `04_LINE選單資源 (media)/rich_menus`，未綁定的 LINE 原始媒體在 `_staging/line_media`。
新受控附件由背景 worker 在原交易提交後驗證並歸檔；舊檔的識別與下載不改，失敗保留暫存供核對。本機開發使用非 NAS 根目錄時，保留既有明確合約／媒體路徑及舊 staging 讀取；不會自動搬移現存資料，此調整不修改現有 `.env`。

升級會先備份，再在新的資料庫副本執行既有 migration 與資料保留驗證。通過驗證及原帳號連線測試後，才切換正式電腦 `.env` 的資料庫名稱。**升級時的原庫、舊備份及失敗副本都保留。**
復原依[同名復原流程](../../.arch-map/requirements/10A_NAS_Fresh初始化與維護復原規格.md#windows-same-name-restore)進行，庫名與 `.env` 不變，選定備份 A 保留；暫存庫及系統暫存目錄無論成功、失敗都清理；不新增備份 B、跨次進度檔或 `_maintenance/`。替換前驗證未過時保留原庫，不執行替換。
完成後重新啟動工會系統，使用原帳號及 MFA 確認登入、資料查詢與操作。升級切換後已產生新資料時，不能直接切回舊庫而忽略新資料。
失敗時不要清空或重複執行，保留畫面與備份紀錄交給維護人員；備份版本不符會停止切換。

#### 共用 FAQ 的保留資料升級

1. 在候選庫套用相容 schema 後，受控升級會先進行唯讀盤點。若缺少審核對照或遇到歧義，升級保留原庫指向，並留下候選的 `operation.json` 和盤點回執。資料維護者以正式問答的歷史發布紀錄核對分類、舊按鈕文字及必要卡片。
2. 將確認後的 UTF-8 JSON 對照保存於維護人員可讀的位置，在 `.env.nas-maintenance` 設 `NAS_FAQ_REVIEWED_MAPPING_FILE`。JSON 應含審核者 `reviewed_by`、舊分類到穩定 ID 的 `categories`、舊文字到穩定題號的 `legacy_questions`。資料維護者解決歧義，維護操作人員執行升級。獨立回填 CLI 的寫入只用於本機隔離測試庫。
3. 維護入口在候選庫回填後用新連線讀回正式題目、舊文字及版面，通過保留資料檢查後留下就緒憑證。只有就緒憑證和候選指紋再次核對通過，才更新 `.env` 的 `DB_DATABASE`。重新啟動 API 和 LINE worker 後，兩者依同一憑證讀共用題庫。
4. 失敗時保留備份、候選及操作回執。維護人員可沿 canonical preserve CLI 的 `--apply` 續接原候選，使用原授權、`--plan-receipt`、`--operation-receipt` 與 `--faq-reviewed-mapping`，再走原有 `--verify` 與 `--switch`。Windows 重新執行安全升級會建立隔離候選。若已嘗試寫入而對照需修正，先保留該候選再用原庫快照建立乾淨候選。未切換時可按既有維護流程啟動原服務。切換後保留現行庫與已發布資料，依備份與新寫入狀況處理服務復原。 [FAQ 切換契約](../../.arch-map/domains/external-integration/subsystems/line/modules/faq-chat-contract.md#db-交接與切換)

#### 技術人員：正式機的一次設定

1. 準備 MySQL 8 的 `mysql.exe` 與 `mysqldump.exe`，加入正式機 PATH。保留原 `.env`，勿複製開發機設定覆蓋正式環境。
2. 確認指定 `.env` 的 MySQL 主機、連接埠及庫名。維護帳密未另填時沿用 `.env`；需要不同帳密或備份位置時才使用選填維護設定檔。不得將密碼或包含個資的備份提交 Git。
3. 備份連線需能完整讀取目標資料、定義及 routine／trigger／event metadata，並維持唯讀 session；維護連線需能建立與維護 `lu_nas_*` 副本，以及把原 runtime／backup 帳號既有 schema 層級權限等量授予新副本。已有完整全域管理權且無部分撤權的帳號不新增授權，仍須用原帳密連線副本核對。工具不修改密碼或原庫權限。角色／細粒度權限不會自動升格，遇到時由原權限維護者處理。
4. 若使用 `.env.nas-maintenance`，僅限正式執行帳號及管理者讀取。密碼不進參數、Git、畫面或 receipt；含空白或 `#` 時保留 dotenv 引號。TLS 沿用原 `.env` 的 DB_SSL_*，不自動降級。
5. 依上方優先順序選擇備份位置，確認正式 Windows 執行帳號可讀寫。先做三入口的 `--dry-run`（零連線、零寫入），再由維護人員執行首次備份與隔離復原驗收，最後啟用每日排程。備份區不供業務附件探索或網頁下載。
6. Task Scheduler 工作由正式執行帳號擁有，API 亦須在該 Windows 帳號下執行。修改時間不需要重新輸入密碼。

頁面顯示備份區狀態與最近結果，啟用排程時實測寫入及讀回。目的地不可用時保留去敏失敗狀態；不得把同一主機或同一磁碟上的副本當成完整災難備援。舊測試備份不自動搬移、刪除或改格式。

SQL 不包含 MySQL 帳號／GRANT、照片／附件、Windows 設定與 MFA 加密金鑰；這些須另外安全保存。
若 MySQL／NAS 已無法啟動，先由維護人員恢復 MySQL 8 服務與原帳號，再用復原腳本。
不要把 SQL 備份當成整台 NAS 或整套應用程式的完整災難備份。

首次空庫建置仍由技術人員使用低階 `python -m scripts.initialize_nas_schema --apply`（或 Unix `.sh`）；此路徑拒絕覆蓋非空庫，不是三個日常 Windows 入口的一部分。

Compose 統一管理本機 Docker MySQL（`db`／`mysql_db`）與 Redis（`redis`／`union_redis`），兩者均僅綁定 `127.0.0.1` loopback。請勿使用 `down -v` 清除具名 `mysql-data` 資料卷。

先確認本機 `.env` 已設定資料庫連線與儲存根目錄，例如：

```dotenv
APP_ENV=development
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=union_app
DB_PASSWORD="replace_with_application_db_password"
DB_DATABASE=union_db
REDIS_URL=redis://127.0.0.1:6379/0
```

IP、port、帳號及資料庫名稱請依實際本機容器設定修改；密碼含 `#` 或空白時請保留引號。
Process environment 的 `DB_*` 優先於 `.env`，readiness 與 API 使用同一組設定。
若原本使用不同的 Redis port，也要同步修改 `REDIS_PORT` 與 `REDIS_URL`。

空白庫建置完成後，可用標準入口啟動並檢視狀態：

```powershell
.\scripts\launchers\start_local_development.bat --dry-run
.\scripts\launchers\start_local_development.bat
```

```bash
./scripts/launchers/start_local_development.sh --dry-run
./scripts/launchers/start_local_development.sh
```

`--dry-run` 不連線資料庫。若要只驗證連線與 schema、不啟動任何服務，可執行：

```powershell
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
