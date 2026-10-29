# Module: runtime-supervision

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以單一 owned Windows supervisor 啟動並監督 FastAPI、React 與各背景 worker。Private API shared key 依序沿用明確 process value、本機 `.env` 現有值，僅兩者都缺少時產生當次臨時值，並由所有 child 共用；API ready 後先通過無副作用認證握手，才能啟動 worker。

## Implementation
- Windows management entry: `Windows管理.bat`、`scripts/launchers/manage_windows.ps1` — single daily management surface using the existing supervisor and run-bound maintenance channel.
- Windows source handoff: `scripts/package_windows_runtime.py` — secret-filtered current program ZIP with source hash manifest, reusing NAS `include_source`; no configuration or runtime data.
- Windows 遠端專用入口：`scripts/launchers/start_windows_remote.bat`、`scripts/windows_remote_runtime.py`，操作由 `scripts/launchers/WINDOWS-REMOTE.md` 承接。建置驗證靜態 artifact，僅 loopback 5173 的 `/test/` 與 `/test/api/`；Gateway 不擁有業務規則，API 保留原授權／writer。supervisor 只在明確 artifact 環境 binding 時改用靜態 Gateway，不啟動 Vite；原 DB gate／worker／cleanup 不變。`--prepare` 不啟動服務、不接觸 DB 或 Cloudflare。測試 `test_windows_remote_runtime.py` 位於既有 Module root。
- Windows Cloudflare 連線：`deployment/windows-remote/path-router.mjs` 只轉送 root `/test` segment 至獨立受 Access 保護的 origin，不改 root DNS／既有 Tunnel。`start_windows_remote.bat --connect` 由原 supervisor 監督 API、static gateway 與 token-file cloudflared；背景工作／推播沿用本機標準啟動規則，不因遠端連線額外停用。`test_windows_remote_router.mjs` 與既有 Python supervisor／gateway tests 共用本 Module test root。
- Windows 前端獨立換版：`scripts/launchers/start_windows_remote.bat --update-frontend` 先建置／驗證新 artifact，再由 `scripts/launchers/windows_frontend_control.ps1` 經本機 run-bound request 交由同一 supervisor 只重啟 Remote React。新版啟動失敗回復原 artifact，前端失敗不連帶停止 API／Worker／Tunnel；舊 supervisor 可按 PID／native start time 與 role 一次性接手既有程序，不進入 DB gate／完整啟動／`.env`。測試 `test_windows_frontend_update.py` 位於本 Module root；正式邊界見 Deployment §5.4。
- Windows LINE Webhook 部署：同一 Windows Tunnel 另以 `line.chrishzc.com` 精確 `/webhook/line/?` 路徑連至執行中 API 8000，無人員 Access；canonical handler／LINE 簽章與 inbox owner 不變，管理與私人路徑由 Tunnel catch-all 拒絕。Cloudflare 外部設定與人工 Verify 交接記於 `scripts/launchers/WINDOWS-REMOTE.md`，不讀寫 `.env`、不把此接線擴成公開 LIFF／管理 API。
- Windows 統一操作：根目錄 `Windows管理.bat` → `scripts/launchers/manage_windows.ps1` → 既有 supervisor；整組停止重用 frontend-control run-bound channel，新增 starting／ready／stopping／stopped／failed 與 cleanup-confirmed readback，不新增公開維運 API。舊 `start_windows_remote.bat` 只轉接參數；舊開發／NAS／DB 維護入口仍有各自 consumer，不退役。
- Windows 獨立主機來源包：`scripts/package_windows_runtime.py` 重用 `scripts/package_nas_preview.py:include_source` 的秘密過濾，排除 runtime data／ignored 設定，附來源雜湊 manifest，不包含資料或 Tunnel token；`scripts/launchers/WINDOWS-REMOTE.md` 承接安裝、換機及純人工 Cloudflare 設定。`test_windows_manager.py` 位於本 Module test root，保護封裝不讀秘密及更新 build-before-stop；既有 frontend lifecycle test 同時驗證整組停止。
- Windows 同版地端／遠端：`scripts/windows_remote_runtime.py` 以同一 artifact 提供 loopback `/admin/` 別名及 `/test/`，非 loopback Host 拒絕 `/admin/`；兩者的 assets／API 使用 artifact 既有 `/test/` prefix。完整啟動保留既有 worker set，切換共用網址採人工整組停舊機、再啟新機，不承諾跨機互斥或資料同步。
- primary: `scripts/launchers/supervise_local_runtime.ps1`
- private cycle composition: `api/dependencies/private_operations.py` — check-only handshake／heartbeat；正常 durable cycle 先 discover confirmed arrangements 與 due completion，再執行既有 canonical worker，不自行寫 Domain root。
- entrypoint: `scripts/launchers/start_local_development.bat`
- NAS entrypoints: `scripts/launchers/start_nas_development.bat`、`scripts/launchers/start_nas_development.sh` — 設定 development／NAS target，委派標準入口。
- database readiness: `scripts/check_runtime_database.py` — 沿用 API 的 DB／TLS 設定，以唯讀 session 呼叫 migration canonical schema gate；不執行更新。
- Unix entrypoint: `scripts/launchers/start_local_development.sh`
- dependency preflight: `scripts/launcher_preflight.py`
- Compose: `docker-compose.yml` — 只管理 Redis；MySQL 由 `.env`／process environment 指定的外部服務提供。
- local-bypass Docker transport: `scripts/launchers/local_react_gateway.py`
- NAS isolated login preview: `deployment/nas-test/compose.yaml`、`deployment/nas-test/Dockerfile`、`deployment/nas-test/nas.sh`；`scripts/package_nas_preview.py` 準備無本機秘密的 build context 與真實歷史 React source，`scripts/nas_test_runtime.py` 僅建立獨立 `lu_test_nas_preview` 設定並以 production 登入啟動。
- DSM GUI handoff: `scripts/package_nas_preview.py --synology-from` 沿用已驗證映像與原包初始化 SQL，產生一次性 prepare、主 app、最後手動 line-check 三個分開目錄的 Compose；操作由 `deployment/nas-test/README.synology.md` 說明。管理員透過容器內建終端機的既有 bootstrap 建立，不新增公開註冊入口。
- GUI bootstrap transport 明確設定 UTF-8、將原 grants here-document 轉成同義 SQL，最後才寫入初始化完成標記；啟動 helper 以唯讀檔案掛入已下載映像，schema gate 使用 manifest verifier 所需的 tuple cursor，不改 canonical DDL／seed／權限規則。
- `scripts.nas_test_runtime:management_preview_app` 是 NAS 管理測試 factory：保留正式登入／MFA 與 Private API，移除 LINE child router 及 `api.routes.line_*` 路由；只執行 canonical knowledge catalog startup，無需偽造 LINE provider credentials。不是完整 LINE production 入口。
- LINE preview startup: `scripts/run_line_worker.py` 的 `--check` 只執行 Private API 認證握手，不進入任何 work cycle。
- Current NAS web-setup r2 image: `scripts/nas_appliance.py`、`deployment/nas-test/Dockerfile.web-setup`、`deployment/nas-test/compose.web-setup.yaml`；`scripts/package_nas_preview.py --web-setup-from` 將初始化 SQL／helper／首次設定表單一起包進新映像，單一 Compose 自動初始化 named volumes，API 讀取設定後降為 UID 1000。無部署啟用碼、固定網址必填或額外 8 並行限制；HTTPS 維持現況，NAS 憑證／代理仍待確認。PDF／匯入／背景工作程式保留，主專案不自動執行工作。操作與驗收由 `deployment/nas-test/README.web-setup.md` 承接；前版包保留作已交付的隔離測試版本。
- NAS r2 最後手動 LINE startup 專案 `deployment/nas-test/line-check.web-setup.yaml` 透過 `nas_appliance line-check` 載入 Worker CLI 的 `--help`，無網路／資料卷、不要求 OIDC 或認證握手；只驗證程式可載入，不代表實際工作可運作。標準 `scripts/run_line_worker.py --check` 的認證行為不變。
- NAS 完整服務新入口：`scripts/nas_security_runtime.py`、`api/nas_apps.py`、`deployment/nas/compose.yaml`、`deployment/nas/Dockerfile`；管理與對外 LINE API 分離，初次 root 沿用 `api/routes/nas_setup.py:attach_setup`，LINE 保留受驗證 LIFF 申請／日誌／照片入口。初始化受 canonical compact schema gate 保護；不覆寫舊安裝。此來源取代新部署的舊 OIDC 假設，不代表已交付 r2 映像更新。
- NAS machine auth：`infrastructure/runtime/worker_credentials.py`、`api/dependencies/internal_service_auth.py`、`infrastructure/http/private_operations_client.py`；逐 Worker token、API 只有 verifier、HTTPS／CA、憑證決定 service。`scripts/run_service_monitor.py` 的內部探測使用相同私人 CA。
- NAS GUI current template：`deployment/nas/compose.yaml`、`deployment/nas/.env.example`、`deployment/nas/README.md`；單檔 Compose 以 `.env` 的 `COMPOSE_PROFILES` 逐組啟動，預設只有基本組。2026-10-20 新安裝採 Synology DDNS／Let’s Encrypt／DSM 內網反向代理：管理 API 不發布 host port，management-egress 使用 NAS_PROXY_SUBNET／NAS_PROXY_API_IP 固定 bridge 位址供同機 DSM HTTPS 轉送，瀏覽器使用 DSM 公信入口（文件預設 19443）。檔案仍使用指定空白 bind roots；公開 LINE 不掛正式業務檔案，經專用 line-media-control 網路及 line-media-proxy token 呼叫私人檔案 API。主檔已含選用 cloudflared，GUI 不需 tunnel overlay。
- GUI initializer 只處理新安裝：非空檔案根目錄在寫入前拒絕，初始化產生五個 Worker 加照片代理六組獨立 token；管理憑證納入設定的 NAS IPv4／可選 hostname，公開 CA 副本輸出至 app-data 供操作者信任；既有標記安裝不補造或輪替秘密。
- NAS 維護：`deployment/nas/README.md` 定義原專案的停止／依賴順序啟動、保留資料重建、無 DB 變更換版與回復、冷備份及獨立還原範圍。正式 Compose 不設定 NanoCPUS，data 引用既有 `${COMPOSE_PROJECT_NAME}_data` internal 網路；新隔離測試自行準備專用網路，不借用 NAS／既有 Docker 資料。opt-in lifecycle test 與 container probe 位於下列 Module root，不建置／推送映像。
- NAS 憑證維護：`scripts/nas_certificate_maintenance.py` 與 `deployment/nas/maintain-certificates.sh`，由 DSM 排程協調、certificates profile 一次性無網路簽發；`deployment/nas/CERTIFICATES.md` 承接安裝／通知教學。既有初始化仍不覆寫舊安裝，首次排程將 legacy CA 導入可續期信任；兩組 CA 分離、先雙重信任再換 leaf、保留重疊期、可回復及續跑。簽發容器不掛 DB 密碼、業務資料或 Docker socket；DB probe 沿用 bootstrap 讀設定後降為 UID 1000，再做 scoped 唯讀連線。實際 DSM 啟用與通知須另驗。
- NAS MySQL client config：`deployment/nas/mysql-client.cnf` 由 initializer 複製至 bootstrap，並掛入 `/etc/mysql/conf.d`，讓 fresh SQL 與 seed 以 UTF-8 執行。私人 API 憑證包含 strict chain 所需識別資訊；管理端另自動產生既有 PDF final-preview HMAC key。
- NAS build context：`scripts/package_nas_preview.py --secure` 沿用秘密過濾與真實 previous React artifact，不上傳映像；`deployment/nas/compose.tunnel.yaml` 只連 public LINE origin，`cloudflared.example.yaml` 拒絕私人路徑；`deployment/nas/README.md` 記錄配置與部署驗收順序。

## Contracts
- NAS Cloudflare 雙入口：`scripts/nas_appliance.py:_trusted_proxies` 保留 DSM gateway／loopback，只加明確 literal connector IP；`deployment/nas/compose.yaml` 使用 remote-managed token-file 與兩個專用 internal origin 網路。`scripts/package_nas_preview.py --operations-validation` 在必要本機驗證通過後產生無秘密的整合 ZIP、完整 Tunnel 啟用版 Compose 與唯讀 runtime 程式；原 .env 不讀不改，不建置映像。`deployment/nas/CLOUDFLARE.md`／`DSM-SETUP.md` 承接 Access whole-host、指定信箱、原網站 MFA、LINE 簽章／本人授權及實際上線驗收。`test_nas_cloudflare_tunnel.py`／`test_nas_tunnel_docker.py` 位於本 Module root；實際 Cloudflare token／Access 寄信不由本機模擬冒充通過。

- NAS 線上 SQL 備份：`deployment/nas/backup-database.sh` 與 `deployment/nas/SQL-BACKUPS.md`，DSM 每日 03:00、獨立管理者備份資料夾、永久保存。僅匯出所屬非空 InnoDB 資料庫的一致性快照與 stored programs，不停止服務、不改 Compose／.env、不包含業務檔案／金鑰／MySQL 系統帳號。`test_nas_sql_backup.py` 位於下列 Module test root，驗證 host 失敗隔離及 opt-in MySQL 併發寫入／獨立還原。

- session key 不寫入 `.env`、不輸出，且不透過 command argument 傳遞。
- API readiness 不等於 Private API authentication readiness；認證握手失敗時 fail closed，不啟動任何 worker。
- 舊 preview handoff 是歷史隔離測試版本；新 NAS 完整服務 source 不使用 Google OIDC。MySQL／Redis 不發布 host port，LINE check 為手動 profile、獨立機器憑證與 HTTPS，無一般 LINE cycle。既有標準 Compose／launcher 不因 NAS profile 改變。
- 舊 r2 DSM GUI 版本的 LINE check 是獨立手動專案、以 DSM 代理 bridge IP:8080；新完整服務模板改用獨立 line-check profile，仍只 --check，不進行業務週期。現行新安裝的管理 API 不發布埠，DSM 公信入口須套內網來源允許及其餘拒絕，內網 DNS／DSM ACL／實際隔離須實測；DSM 到容器的私人 CA 鏈驗證不得由瀏覽器憑證推定。prepare 無網路，禁止覆寫已有設定／資料。
- supervisor 只清理本次建立且可重新驗證身分的 process tree。
- 標準入口不再啟動 MySQL 容器；NAS 入口拒絕 loopback DB_HOST，dry-run 零連線，schema 非 current 時不啟動 runtime。
- 唯讀 schema 查核：連線最多 5 秒、單次查詢預設最多 30 秒；明確 caller timeout 可縮短，無 retry 或寫入。
- Windows local-bypass 沒有主機 npm 時，由 Docker 執行 Vite，主機 loopback gateway 轉送 relative API 與前端 HTTP／WebSocket；API、gateway 與 Docker published port 均限 loopback，gateway 納入同一 owned supervision。

## Verification
- layout_status: `custom_current`
- layout_basis: 既有 Private Runtime Operations 系統契約檔仍為 API／worker／monitor 的共同 consumer；本次只替換已退役 OIDC 的認證 oracle，保留 local／heartbeat／worker 契約及既有 discovery。新 NAS 專屬測試使用下列 canonical Module root。
- test_root: `tests/test_private_runtime_operations.py`
- test_root: `tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/`
- `test_nas_compose_lifecycle.py` 與 `nas_lifecycle_probe.py` — 本機明確 opt-in 的隔離 Compose／資料卷演練；不代表 DSM GUI 或 NAS 網路已驗證。
- `test_nas_certificate_maintenance.py` — Linux 憑證狀態／TLS／主機協調器與失敗通知退出碼；`test_nas_certificate_docker.py` — 明確 opt-in 的獨立 MySQL／API 換證、回復、原帳號／MFA／檔案及機器認證，沒有 provider 工作週期。

## Provenance
- Windows entrypoint, process ownership and Private API client/auth boundary — `source_observed` — current launcher, supervisor and authenticated private runtime implementation.

## Change triggers
Reconcile when Windows startup ownership, child set, session-key lifecycle, Private API authentication readiness, or focused test root changes.
