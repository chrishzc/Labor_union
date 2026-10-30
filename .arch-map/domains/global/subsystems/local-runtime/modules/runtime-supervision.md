# Module: runtime-supervision

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以單一 owned Windows supervisor 啟動並監督 FastAPI、React 與各背景 worker。Private API shared key 依序沿用明確 process value、本機 `.env` 現有值，僅兩者都缺少時產生當次臨時值，並由所有 child 共用；API ready 後先通過無副作用認證握手，才能啟動 worker。

## Implementation
- primary: `scripts/launchers/supervise_local_runtime.ps1`
- Windows management entry: `Windows管理.bat`、`scripts/launchers/manage_windows.ps1` — single daily management surface using the existing supervisor and run-bound maintenance channel.
- Explicit NAS maintenance menu: options 6/7/8 delegate backup/upgrade/restore to `scripts.nas_database_maintenance` (Global migration §9.5); backup permits a running runtime, upgrade/restore require this installation stopped. No implicit stop/restart or database operation on normal startup. Packaging remains an advanced `-Action package` consumer and is absent from the daily menu.
- Windows source handoff: `scripts/package_windows_runtime.py` — secret-filtered current program ZIP with source hash manifest (`include_source` owned directly in this module); no configuration or runtime data.
- private cycle composition: `api/dependencies/private_operations.py` — check-only handshake／heartbeat；正常 durable cycle 先 discover confirmed arrangements 與 due completion，再執行既有 canonical worker，不自行寫 Domain root。
- entrypoint: `scripts/launchers/start_local_development.bat`
- NAS entrypoints: `scripts/launchers/start_nas_development.bat`、`scripts/launchers/start_nas_development.sh` — 設定 development／NAS target，委派標準入口。
- database readiness: `scripts/check_runtime_database.py` — 沿用 API 的 DB／TLS 設定，以唯讀 session 呼叫 migration canonical schema gate；不執行更新。
- Unix entrypoint: `scripts/launchers/start_local_development.sh`
- dependency preflight: `scripts/launcher_preflight.py`
- Compose: `docker-compose.yml` — 工會電腦本機只管理 Redis；MySQL 由 `.env`／process environment 指定的外部／NAS 服務提供。
- local-bypass Docker transport: `scripts/launchers/local_react_gateway.py`
- LINE worker check: `scripts/run_line_worker.py` 的 `--check` 只執行 Private API 認證握手，不進入任何 work cycle。
- Isolated API composition & setup surface: `api/nas_apps.py`、`api/routes/nas_setup.py:attach_setup` — 管理與對外 LINE API 分離組成，保留受驗證 LIFF 申請／日誌／照片入口與 canonical knowledge catalog startup，並於公開 `line_app()` 掛載 `ResponseCompressionMiddleware`（排除 XLSX 封裝）與排空連線池。
- Machine auth: `infrastructure/runtime/worker_credentials.py`、`api/dependencies/internal_service_auth.py`、`infrastructure/http/private_operations_client.py`；逐 Worker token、API 只有 verifier、HTTPS／CA、憑證決定 service（`test_nas_worker_credentials.py`）。`scripts/run_service_monitor.py` 的內部探測使用相同私人 CA。
- LIFF operation bridge: `api/routes/nas_line_operations.py`、`infrastructure/http/line_operations_client.py` 與 `api/nas_apps.py` 明確組合接案回覆、訂金、服務說明／回饋、手機工會管理及其既有子路由。公開端只轉送原 JSON 契約，管理端私人入口 `/internal/v1/line-operations` 以 `line-operations-proxy` 獨立機器憑證保護，仍執行原 LINE 憑證／綁定／能力／本人範圍／版本與冪等驗證。測試 `test_nas_line_operations.py` 位於本 Module root。
- NAS MySQL DB deployment: `deployment/nas/compose.yaml`、`deployment/nas/.env.example`、`deployment/nas/README.md`、`deployment/nas/mysql-client.cnf` — 2026-10-29 定案 NAS 僅部署純 MySQL 8.0 服務（`db` 容器、`mysql-data` 資料卷、UTF-8 設定與 `/run/mysql-secrets/` 密碼檔掛載，限區網供工會電腦連線，不對外網公開 3306）；`test_nas_test_bundle.py` 驗證純 DB Compose 契約與來源封裝秘密過濾。
- Windows 遠端專用入口：`scripts/launchers/start_windows_remote.bat`、`scripts/windows_remote_runtime.py`，操作由 `scripts/launchers/WINDOWS-REMOTE.md` 承接。建置驗證靜態 artifact，僅 loopback 5173 的 `/test/` 與 `/test/api/`（靜態資源經 `ResponseCompressionMiddleware` Gzip 壓縮並保留 immutable 快取標頭）；Gateway 不擁有業務規則，API 保留原授權／writer。supervisor 只在明確 artifact 環境 binding 時改用靜態 Gateway，不啟動 Vite；原 DB gate／worker／cleanup 不變。`--prepare` 不啟動服務、不接觸 DB 或 Cloudflare。測試 `test_windows_remote_runtime.py` 位於既有 Module root。
- Windows Cloudflare 連線：`deployment/windows-remote/path-router.mjs` 只轉送 root `/test` segment 至獨立受 Access 保護的 origin，不改 root DNS／既有 Tunnel。`start_windows_remote.bat --connect` 由原 supervisor 監督 API、static gateway 與 token-file cloudflared；背景工作／推播沿用本機標準啟動規則，不因遠端連線額外停用。`test_windows_remote_router.mjs` 與既有 Python supervisor／gateway tests 共用本 Module test root。
- Windows 前端獨立換版：`scripts/launchers/start_windows_remote.bat --update-frontend` 先建置／驗證新 artifact，再由 `scripts/launchers/windows_frontend_control.ps1` 經本機 run-bound request 交由同一 supervisor 只重啟 Remote React。新版啟動失敗回復原 artifact，前端失敗不連帶停止 API／Worker／Tunnel；舊 supervisor 可按 PID／native start time 與 role 一次性接手既有程序，不進入 DB gate／完整啟動／`.env`。測試 `test_windows_frontend_update.py` 位於本 Module root；正式邊界見 Deployment §5.4。
- Windows LINE Webhook 部署：同一 Windows Tunnel 另以 `line.chrishzc.com` 精確 `/webhook/line/?` 路徑連至執行中 API 8000，無人員 Access；canonical handler／LINE 簽章與 inbox owner 不變，管理與私人路徑由 Tunnel catch-all 拒絕。Cloudflare 外部設定與人工 Verify 交接記於 `scripts/launchers/WINDOWS-REMOTE.md`，不讀寫 `.env`、不把此接線擴成公開 LIFF／管理 API。

## Contracts
- Windows 統一操作：根目錄 `Windows管理.bat` → `scripts/launchers/manage_windows.ps1` → 既有 supervisor；整組停止重用 frontend-control run-bound channel，新增 starting／ready／stopping／stopped／failed 與 cleanup-confirmed readback，不新增公開維運 API。舊 `start_windows_remote.bat` 只轉接參數；舊開發／NAS／DB 維護入口仍有各自 consumer，不退役。
- Windows 獨立主機來源包：`scripts/package_windows_runtime.py` 內聚 `include_source` 秘密過濾，排除 runtime data／ignored 設定，附來源雜湊 manifest，不包含資料或 Tunnel token；`scripts/launchers/WINDOWS-REMOTE.md` 承接安裝、換機及純人工 Cloudflare 設定。`test_windows_manager.py` 位於本 Module test root，保護封裝不讀秘密及更新 build-before-stop；既有 frontend lifecycle test 同時驗證整組停止。
- Windows 同版地端／遠端：`scripts/windows_remote_runtime.py` 以同一 artifact 提供 loopback `/admin/` 別名及 `/test/`，非 loopback Host 拒絕 `/admin/`；兩者的 assets／API 使用 artifact 既有 `/test/` prefix。完整啟動保留既有 worker set，切換共用網址採人工整組停舊機、再啟新機，不承諾跨機互斥或資料同步。
- Migration catalog guard：`scripts.update_local_database.build_additive_preview` 在 canonical runner 未載入時於任何 DB 存取前回報 `migration_catalog_unavailable`。
- NAS 線上 SQL 備份：`deployment/nas/backup-database.sh` 與 `deployment/nas/SQL-BACKUPS.md`，DSM 每日 03:00、獨立管理者備份資料夾、永久保存。僅匯出所屬非空 InnoDB 資料庫的一致性快照與 stored programs，不停止服務、不改 Compose／.env、不包含業務檔案／金鑰／MySQL 系統帳號。`test_nas_sql_backup.py` 位於下列 Module test root，驗證 host 失敗隔離及 opt-in MySQL 併發寫入／獨立還原。
- DSM backup-copy upgrade belongs to Global migration (`scripts/update_nas_database.py`, `deployment/nas/upgrade-database.sh`, `deployment/nas/DATABASE-UPGRADE.md`). SQL backups validate the actual volume's project and logical `mysql-data` labels, allowing the explicitly switched physical volume while still rejecting another project.
- session key 不寫入 `.env`、不輸出，且不透過 command argument 傳遞。
- API readiness 不等於 Private API authentication readiness；認證握手失敗時 fail closed，不啟動任何 worker。
- supervisor 只清理本次建立且可重新驗證身分的 process tree。
- 標準入口不再啟動 MySQL 容器；NAS 入口拒絕 loopback DB_HOST，dry-run 零連線，schema 非 current 時不啟動 runtime。
- 唯讀 schema 查核：連線最多 5 秒、單次查詢預設最多 30 秒；明確 caller timeout 可縮短，無 retry 或寫入。
- Windows local-bypass 沒有主機 npm 時，由 Docker 執行 Vite，主機 loopback gateway 轉送 relative API 與前端 HTTP／WebSocket；API、gateway 與 Docker published port 均限 loopback，gateway 納入同一 owned supervision。

## Verification
- layout_status: `custom_current`
- layout_basis: 既有 Private Runtime Operations 系統契約檔仍為 API／worker／monitor 的共同 consumer；本次只替換已退役 OIDC 的認證 oracle，保留 local／heartbeat／worker 契約及既有 discovery。Windows／NAS 維運專屬測試使用下列 canonical Module root。
- test_root: `tests/test_private_runtime_operations.py`
- test_root: `tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/`

## Provenance
- Windows entrypoint, process ownership and Private API client/auth boundary — `source_observed` — current launcher, supervisor and authenticated private runtime implementation.

## Change triggers
Reconcile when Windows startup ownership, child set, session-key lifecycle, Private API authentication readiness, or focused test root changes.
