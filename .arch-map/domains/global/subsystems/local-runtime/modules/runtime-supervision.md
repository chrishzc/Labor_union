# Module: runtime-supervision

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以單一 owned Windows supervisor 啟動並監督 FastAPI、React 與各背景 worker。Private API 統一使用 `local_shared_key`（不限 `APP_ENV`）：`supervise_local_runtime.ps1` 依序沿用明確 process value、本機 `.env` 現有值，僅兩者都缺少時產生當次臨時值，並由所有 child 共用。API ready 後先通過無副作用認證握手，才能啟動 worker。

## Implementation
- primary: `scripts/launchers/supervise_local_runtime.ps1`
- Windows management entry: `Windows管理.bat`、`scripts/launchers/manage_windows.ps1` — single daily management surface using the existing supervisor and run-bound maintenance channel.
- Root maintenance: option `11` dispatches `scripts/root_account_maintenance.py` under the Windows manager lock and checks that the managed runtime has stopped. Access owns verification and account changes ([authentication-session](../../../../external-integration/subsystems/access/modules/authentication-session.md)).
- Explicit NAS maintenance: see [Windows 管理器的資料庫維護入口](#windows-管理器的資料庫維護入口). Normal startup does not stop or restart services for maintenance or invoke database maintenance. Packaging remains an advanced `-Action package` consumer, not a daily menu action.
- Windows source handoff: `scripts/package_windows_runtime.py` — secret-filtered current program ZIP with source hash manifest (`include_source` owned directly in this module); no configuration or runtime data.
- private cycle composition: `api/dependencies/private_operations.py` — check-only handshake／heartbeat；正常 durable cycle 先 discover confirmed arrangements 與 due completion，再執行既有 canonical worker，不自行寫 Domain root。
- A normal NAS/production durable cycle also runs the existing bounded controlled-file finalize runner for new shared-root 01–04 locators, including an explicit UNC root in source mode (APP_ENV=development). Local development/test, missing root configuration and check-only handshakes do not run it; no legacy file scan/migration. Root resolution and directory layout remain Global controlled-files owned.
- entrypoint: `scripts/launchers/start_local_development.bat`
- database readiness: `scripts/check_runtime_database.py` — 沿用 API 的 DB／TLS 設定，以唯讀 session 呼叫 migration canonical schema gate；不執行更新。同名復原由 [Migration 復原協調](../../migration/modules/preserved-database-upgrade.md#同名復原協調與接續) 提供 sanitized 狀態，readiness gate 於啟動前拒絕尚未完成目標驗證的復原。管理器的復原入口沿用既有管理鎖並核對殘留 runtime，獨立復原批次由 maintenance adapter 取得同一管理鎖；writer 仍由 Migration 擁有。
- Unix entrypoint: `scripts/launchers/start_local_development.sh`
- dependency preflight: `scripts/launcher_preflight.py`
- Compose: `docker-compose.yml` — 單一工會主機統一編排 MySQL 8.0（`db`／`mysql_db`）、Redis 7（`redis`／`union_redis`）與 `registration` profile（`registration-redis`、`registration-intake`、`registration-token-verifier`），所有對主機發布連接埠均僅綁定 `127.0.0.1` loopback。
- local-bypass Docker transport: `scripts/launchers/local_react_gateway.py`
- LINE worker check: `scripts/run_line_worker.py` 的 `--check` 只執行 Private API 認證握手，不進入任何 work cycle。
- Isolated API composition & setup surface: `api/nas_apps.py` — 管理與對外 LINE API 分離組成；management 沿用 `api.main` 掛載的 Access-owned `api/routes/admin_setup.py`，不另掛安裝模式，並於啟動時自動補齊基準 LINE 設定與內建知識庫。`line_app()` 直接掛載受驗證 LIFF 入口、`line_table_images.router`、`ResponseCompressionMiddleware`（排除 XLSX 封裝）與排空連線池。
- Windows setup proxy: `scripts/windows_remote_runtime.py` — setup API 使用已驗證的 Host 與 request scheme 供 API 同源檢查，外來 forwarded headers 仍剔除；不擁有 root 狀態或建帳 writer。
- Machine auth: `api/dependencies/internal_service_auth.py`、`infrastructure/http/private_operations_client.py`；統一以 `local_shared_key` 驗證內部操作與服務識別綁定，非 `local_shared_key` 模式 fail closed。測試見 `test_private_runtime_operations.py`。
- LINE public app composition: `api/nas_apps.py` 直接組合接案回覆、訂金、服務說明／回饋、手機工會管理、表格圖片及其既有子路由（含 `staff_leave_intake` 延後結果驗證路由與 410 退役端點）。測試 `test_nas_line_operations.py` 位於本 Module root。
- Single-host Docker stateful deployment: `docker-compose.yml` — 同機部署 MySQL 8.0（`db` 容器 `mysql_db`、`mysql-data` 資料卷、UTF-8／UTC 設定與 `127.0.0.1:3306` loopback 綁定）、Redis 7（`redis` 容器 `union_redis`、`127.0.0.1:6379` loopback 綁定），以及可由 `--profile registration` 啟用之隔離待審容器（`registration-redis` `127.0.0.1:6380`、`registration-intake` `127.0.0.1:8080` 與 `registration-token-verifier`）；`test_nas_test_bundle.py` 與 `test_docker_compose_local_security.py` 驗證單機 Compose 安全契約與來源封裝秘密過濾。
- Windows 遠端專用入口：`scripts/launchers/start_windows_remote.bat`、`scripts/windows_remote_runtime.py`，操作由 `scripts/launchers/WINDOWS-REMOTE.md` 承接。建置驗證靜態 artifact（`scripts/build_react_admin_artifact.py` 洗滌非白名單 `VITE_*` 變數並由 `.vite/manifest.json` 寫入 `immutable_assets`，`infrastructure/runtime/react_admin_artifact.py` 向後相容舊版 v1 產物回復），僅 loopback 5173 的 `/test/` 與 `/test/api/`（靜態資源經 `ResponseCompressionMiddleware` Gzip 壓縮，僅已驗證內容版本化純 JS／CSS 發出 `private, max-age=31536000, immutable` 與內部資格標頭，API 代理剝除該標頭並維持 `no-store`）；Gateway 不擁有業務規則，API 保留原授權／writer。supervisor 只在明確 artifact 環境 binding 時改用靜態 Gateway，不啟動 Vite；原 DB gate／worker／cleanup 不變。`--prepare` 不啟動服務、不接觸 DB 或 Cloudflare。測試 `test_windows_remote_runtime.py` 位於既有 Module root。
- Windows Cloudflare 連線：`deployment/windows-remote/path-router.mjs` 只轉送 root `/test` segment 至獨立受 Access 保護的 origin，不改 root DNS／既有 Tunnel；上游 `fetch` 維持 `no-store`（edge bypass），僅通過路徑、方法、200 狀態、MIME、無 Cookie／redirect 與內部資格證明之純 JS／CSS 設定瀏覽器私有 `immutable` 並剝除內部標頭，其餘一律 `no-store`。`start_windows_remote.bat --connect` 由原 supervisor 監督 API、static gateway 與 token-file cloudflared；背景工作／推播沿用本機標準啟動規則，不因遠端連線額外停用。`test_windows_remote_router.mjs` 與既有 Python supervisor／gateway tests 共用本 Module test root。
- Windows 前端獨立換版：`scripts/launchers/start_windows_remote.bat --update-frontend` 先建置／驗證新 artifact，再由 `scripts/launchers/windows_frontend_control.ps1` 經本機 run-bound request 交由同一 supervisor 只重啟 Remote React。新版啟動失敗回復原 artifact，前端失敗不連帶停止 API／Worker／Tunnel；舊 supervisor 可按 PID／native start time 與 role 一次性接手既有程序，不進入 DB gate／完整啟動／`.env`。測試 `test_windows_frontend_update.py` 位於本 Module root；正式邊界見 [Deployment](../../../../../requirements/18_Global_Deployment與治理正式規格.md) §5.2「前端獨立換版」。
- Windows LINE Webhook 部署：同一 Windows Tunnel 另以 `line.chrishzc.com` 精確 `/webhook/line/?` 路徑連至執行中 API 8000，無人員 Access；canonical handler／LINE 簽章與 inbox owner 不變，管理與私人路徑由 Tunnel catch-all 拒絕。Cloudflare 外部設定與人工 Verify 交接記於 `scripts/launchers/WINDOWS-REMOTE.md`，不讀寫 `.env`、不把此接線擴成公開 LIFF／管理 API。

### Windows 管理器的資料庫維護入口

[行為與驗收的權威條文：NAS 維護規格](../../../../../requirements/10A_NAS_Fresh初始化與維護復原規格.md#windows-管理器的安全升級契約)。Local Runtime 擁有管理器的參數、選單分派與受管服務狀態檢查；Migration 擁有維護操作、資料庫選路及結果。

| 啟動介面 | 互動升級 | 指定動作 |
|---|---|---|
| 根目錄 `Windows管理.bat` | 不帶參數進入管理器，選 `7`。 | 以 `-Action database-upgrade` 啟動；BAT 將參數轉交 PowerShell。 |
| 直接啟動 `scripts/launchers/manage_windows.ps1` | 預設 `menu`，選 `7`。 | 直接指定 `-Action database-upgrade`。 |

四種走法匯入 `Invoke-ManagerAction` 的 `database-upgrade`，再到 `Invoke-DatabaseMaintenance 'upgrade'`。Python 環境不存在或同一安裝仍有受管服務時，管理器回報錯誤而不呼叫維護模組；通過才委派 `scripts.nas_database_maintenance upgrade`。其 `backup` 和 `restore` 分別由選項 `6`、`8` 分派，不是升級別名。受管服務運作時仍允許備份，升級與復原則受上述檢查限制。獨立的 NAS 升級批次不經管理器，見 [Migration 架構](../../migration/modules/preserved-database-upgrade.md#windows-nas-維護交接)；不要把管理器前置檢查套用到所有入口。

管理器針對受管服務狀態的前置檢查及委派可查 [既有管理器測試](../../../../../../tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/test_windows_manager.py#L358-L394) 的 `test_database_delegate_requires_stop_for_upgrade_restore_and_propagates_failure`。它以替身檢查服務運作時允許備份、拒絕升級與復原且不代停服務、停止後委派，以及備份子程序失敗時管理器會報錯；不驗證 MySQL 或實機維護結果。

## Contracts
- Windows 統一操作：根目錄 `Windows管理.bat` → `scripts/launchers/manage_windows.ps1` → 既有 supervisor；整組停止重用 frontend-control run-bound channel，新增 starting／ready／stopping／stopped／failed 與 cleanup-confirmed readback，不新增公開維運 API。舊 `start_windows_remote.bat` 只轉接參數；舊開發／NAS／DB 維護入口仍有各自 consumer，不退役。
- Windows 獨立主機來源包：`scripts/package_windows_runtime.py` 內聚 `include_source` 秘密過濾，排除 runtime data／ignored 設定，附來源雜湊 manifest，不包含資料或 Tunnel token；`scripts/launchers/WINDOWS-REMOTE.md` 承接安裝、換機及純人工 Cloudflare 設定。`test_windows_manager.py` 位於本 Module test root，保護封裝不讀秘密及更新 build-before-stop；既有 frontend lifecycle test 同時驗證整組停止。
- Windows 同版地端／遠端：`scripts/windows_remote_runtime.py` 以同一 artifact 提供 loopback `/admin/` 別名及 `/test/`，非 loopback Host 拒絕 `/admin/`；兩者的 assets／API 使用 artifact 既有 `/test/` prefix。完整啟動保留既有 worker set，切換共用網址採人工整組停舊機、再啟新機，不承諾跨機互斥或資料同步。
- Migration catalog guard：`scripts.update_local_database.build_additive_preview` 在 canonical runner 未載入時於任何 DB 存取前回報 `migration_catalog_unavailable`。
- 本機備份／安全升級／復原由 Windows 三入口（`scripts/nas_database_maintenance.py`）對同機 Docker MySQL 執行，不再經獨立 Synology DSM 腳本（`deployment/nas/` 與 `update_nas_database.py` 已移除）。
- 本機 `local_auth` 的 session key 不寫入 `.env`、不輸出，且不透過 command argument 傳遞。
- API readiness 不等於 Private API authentication readiness；認證握手失敗時 fail closed，不啟動任何 worker。
- supervisor 只清理本次建立且可重新驗證身分的 process tree。
- 單機標準入口先透過 `docker compose up -d --wait db redis` 啟動本機 MySQL 與 Redis 容器，再執行唯讀 schema 查核（dry-run 零連線，schema 非 current 時不啟動 runtime）。
- 唯讀 schema 查核：連線最多 5 秒、單次查詢預設最多 30 秒；明確 caller timeout 可縮短，無 retry 或寫入。
- Windows local-bypass 沒有主機 npm 時，由 Docker 執行 Vite，主機 loopback gateway 轉送 relative API 與前端 HTTP／WebSocket；API、gateway 與 Docker published port 均限 loopback，gateway 納入同一 owned supervision。

## Verification
- layout_status: `custom_current`
- layout_basis: 既有 [Private Runtime Operations 系統契約測試](../../../../../../tests/test_private_runtime_operations.py)仍為 API／worker／monitor 的共同 consumer；本次只替換已退役 OIDC 的認證 oracle，保留 local／heartbeat／worker 契約及既有 discovery。Windows／NAS 維運專屬測試使用下列 canonical Module root。
- test_root: `tests/test_private_runtime_operations.py`
- test_root: `tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/`

## Provenance
- Windows entrypoint, process ownership and Private API client/auth boundary — `source_observed` — current launcher, supervisor and authenticated private runtime implementation.

## Change triggers
Reconcile when Windows startup ownership, child set, session-key lifecycle, Private API authentication readiness, or focused test root changes.

### 正式管理路徑切換

Windows 管理閘道沿用原授權組成，可在完整建置與啟動時選擇 `WINDOWS_REMOTE_PREFIX=/admin`，未選仍保留 `/test` 作為切換前的部署路徑。新建置、靜態閘道與健康探測都採同一路徑。切換後原 `/test/` 網頁導向 `/admin/`；既有 `/test/api/` 仍轉送同一 loopback API 並保留方法、內容和授權，不重送。Edge 路由與 Access 需先準備並另外核驗；不更動根站、LINE Webhook 或正式業務資料。[Windows 操作說明](../../../../../../scripts/launchers/WINDOWS-REMOTE.md#正式管理網址切換待核准及驗收)
