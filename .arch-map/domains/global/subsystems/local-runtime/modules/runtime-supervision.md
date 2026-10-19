# Module: runtime-supervision

## Parent
- domain: `global`
- subsystem: `local-runtime`

## Responsibility
以單一 owned Windows supervisor 啟動並監督 FastAPI、React 與各背景 worker。Private API shared key 依序沿用明確 process value、本機 `.env` 現有值，僅兩者都缺少時產生當次臨時值，並由所有 child 共用；API ready 後先通過無副作用認證握手，才能啟動 worker。

## Implementation
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

## Contracts
- session key 不寫入 `.env`、不輸出，且不透過 command argument 傳遞。
- API readiness 不等於 Private API authentication readiness；認證握手失敗時 fail closed，不啟動任何 worker。
- NAS preview 預設只發布 loopback HTTP；MySQL／Redis 不發布 host port；LINE check 為手動 profile、production OIDC，缺憑證時 blocked，無一般 LINE cycle。既有標準 Compose／launcher 不因 preview 改變。
- DSM GUI 版本的 LINE check 改為獨立手動專案；prepare 無網路、禁止覆寫已有設定／資料。API 不發布 host port，DSM HTTPS 反向代理以 API 的 bridge IP:8080 連入並限制單一工會電腦來源，不需 SSH；重新部署須核對容器 IP，憑證／NAS 來源規則須由部署者設定與實測。
- supervisor 只清理本次建立且可重新驗證身分的 process tree。
- 標準入口不再啟動 MySQL 容器；NAS 入口拒絕 loopback DB_HOST，dry-run 零連線，schema 非 current 時不啟動 runtime。
- 唯讀 schema 查核：連線最多 5 秒、單次查詢預設最多 30 秒；明確 caller timeout 可縮短，無 retry 或寫入。
- Windows local-bypass 沒有主機 npm 時，由 Docker 執行 Vite，主機 loopback gateway 轉送 relative API 與前端 HTTP／WebSocket；API、gateway 與 Docker published port 均限 loopback，gateway 納入同一 owned supervision。

## Verification
- test_root: `tests/domains/global/subsystems/local-runtime/modules/runtime-supervision/`

## Provenance
- Windows entrypoint, process ownership and Private API client/auth boundary — `source_observed` — current launcher, supervisor and authenticated private runtime implementation.

## Change triggers
Reconcile when Windows startup ownership, child set, session-key lifecycle, Private API authentication readiness, or focused test root changes.
