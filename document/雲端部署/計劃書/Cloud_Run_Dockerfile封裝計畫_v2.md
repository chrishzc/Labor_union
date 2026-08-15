# Cloud Run Dockerfile 正式封裝計畫 v2

文件狀態：已完成計畫驗證（`PLAN_VALIDATION_PASS`）

部署基線：`document/雲端部署/計劃書/單一Cloud VPN計畫書.md`

適用範圍：Cloud Run 5 個資源、Direct VPC egress、HA VPN gateway resource 上的單一 Cloud VPN tunnel（non-HA topology）及地端 NAS MySQL。本文件只規劃映像封裝、啟動與驗證，不執行部署、VPN／firewall 變更或資料庫變更。

安全原則：最小內容、最小權限、唯讀映像、明確 allowlist、未分類資料一律不封裝（fail closed）。單一 tunnel 只降低可用性，不降低映像與身分隔離要求，也不得建立公開 3306 旁路。

## 一、摘要與結論

最終規劃為 **4 份 Dockerfile、4 個映像、部署到 5 個 Cloud Run 資源**：

| Dockerfile | 正式映像 | Cloud Run 資源 | 用途 |
|---|---|---|---|
| `docker/Dockerfile.api` | `union-api` | 1 個 Service | 唯一可經 Direct VPC、單一 VPN tunnel、MySQL mTLS 存取地端 MySQL 的 FastAPI |
| `docker/Dockerfile.ui` | `union-ui` | 1 個 Service | Streamlit 薄 UI，只呼叫 API |
| `docker/Dockerfile.runtime-ops` | `union-runtime-ops` | 1 個 Worker Pool + 1 個 monitor Job | 三種正式 worker 共用一個映像；monitor 同映像、不同命令 |
| `docker/Dockerfile.ingestion` | `union-ingestion` | 1 個 Service | 未來檔案接收服務；正式 entry point 完成後才可建置 |

「5+1」中的 `+1` 是地端 NAS MySQL，不是容器。共用 `runtime-ops` 映像只共用程式與依賴，不共用執行資源、Service Account、環境變數、權限或發布 gate。

相較 v1，映像數與正式程式邊界不變；需要修改的部分是：

1. `union-runtime-workers` 依單一 Cloud VPN 計畫採 **Cloud Run Worker Pool**，不是需要監聽 `PORT` 的 Cloud Run Service。worker supervisor 仍須完整管理三個 worker，但健康判斷改用 process exit、heartbeat、queue lag 與外部 monitor，不建立假 HTTP server。
2. API 啟動與驗收必須明確區分 process liveness 和 authenticated DB readiness。單 tunnel 中斷時 API process 可存活，但 DB operation 必須 typed unavailable 且不得改走公開 3306。
3. VPN PSK、BGP、route、network tag、NAS 私有位址及 MySQL mTLS material 都是部署設定，不得燒進 image。映像只包含讀取受控 runtime configuration 的正式 adapter。
4. 發布驗證增加 tunnel interruption／recovery 行為：中斷時 fail closed，恢復後重新驗證 route、server identity、fresh facts、lease 與 backlog，再恢復 mutation。

目前 live code 尚有以下實作前置條件；未完成前，對應映像必須拒絕建置或不得標記為 production：

1. UI 表單管理仍直接讀寫 `db/form_templates.json` 與 `db/templates/`。須改為 typed API；UI 映像不得攜入這些資料檔。
2. LINE 設定、LIFF 歷史與 rich-menu ID 仍使用可變 `config/*.json`／根目錄 `rich_menu_ids.json`。須移到 API 擁有的耐久儲存，或把不可變 release default 搬到經審核的 `runtime_assets/`。
3. 合約封存、LINE 媒體與 rich-menu 圖片仍存在本機檔案預設路徑。正式環境須改用耐久 object-storage adapter，未設定時 fail closed。
4. `line/line_bot.py` 的 `DEV_REVIEW_NOTIFY_URL` 開發通知路徑須從正式 runtime closure 移除；只讓環境變數為空不足以證明映像沒有開發程序。
5. Worker Pool 需要正式 supervisor，在同一執行個體管理 durable-job、LINE-delivery、incident 三個 worker，正確處理 SIGTERM、子程序失敗及非零 exit；不需要也不得為了通過 Cloud Run Service 規則而新增假 `PORT` server。
6. ingestion 尚無核准且可啟動的正式 entry point，因此 `Dockerfile.ingestion` 只能保留設計，不得建立空殼或假成功映像。

## 二、正式封裝邊界

### 2.1 允許的正式 entry point

| 資源 | 唯一正式啟動命令（計畫值） | 完整啟動條件 |
|---|---|---|
| API Service | `python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT}` | 全部正式 router 可載入；liveness 成功；只有此資源取得 DB secret 與 Direct VPC／VPN route |
| UI Service | `python -m streamlit run ui/app.py --server.address=0.0.0.0 --server.port=${PORT}` | page registry 全部可載入；健康端點成功；沒有 DB driver／DB secret |
| Worker Pool | `python -m scripts.run_runtime_worker_pool` | 同時監督 durable、LINE、incident worker；不監聽 `PORT`；必要子程序永久失敗時 supervisor 非零結束 |
| Monitor Job | `python -m scripts.run_service_monitor --once` | 單次執行有明確 exit code、timeout 與重試界線；不得常駐或自行排程 |
| Ingestion Service | 待正式 entry point 核准後固定 | 必須監聽 `PORT`、完成驗證與 durable enqueue；未核准前禁止建置 |

Worker Pool 僅包含：

- `scripts/run_durable_job_worker.py`
- `scripts/run_line_worker.py`
- `scripts/run_incident_worker.py`

`scripts/run_service_monitor.py` 雖與 worker 共用映像，但不由 worker supervisor 啟動，只供 Cloud Run Job 覆寫 command 使用。Monitor 必須位於獨立故障域，才能在 Worker Pool 異常時仍偵測 heartbeat stale。

### 2.2 明確禁止的 entry point 與程序

下列內容不可出現在 final image，也不可由 production command 間接呼叫：

- `scripts/launchers/start_local_development.bat` 及所有本機／ngrok launcher。
- `scripts/file_watcher.py`、開發檔案監看、hot reload、debug server。
- `scripts/run_knowledge_worker.py`；目前 Knowledge runtime 已停用。
- DB reset、bootstrap、migration、seed、fixture、fake-data、backfill、export/import、資料修復腳本。
- CI、lint、測試、coverage、benchmark、產生器與一次性 operator script。
- `DEV_*` 開發通知或 reviewer callback 路徑。
- API lifespan 內嵌 worker、Worker Pool 假 HTTP health server及公開 3306 fallback。
- VPN client、Tailscale、Nginx、ngrok、Cloud SQL Proxy 或把 IPsec tunnel 建在容器內的程序。

### 2.3 內容 allowlist 與 runtime closure

禁止 `COPY . .` 或整個 repository 複製。每個映像必須有版本化的 `docker/runtime-manifests/<image>.txt`，逐檔列出允許進入 final stage 的檔案；CI 依 manifest 產生內容清單與 SHA-256，未列入或找不到的檔案都使建置失敗。

manifest 必須由下列證據產生及覆核：

1. 從正式 entry point 建立完整 Python import closure。
2. 掃描 `open()`、`Path.read_*`、`FileResponse`、模板／靜態資產查找與動態 import。
3. 載入 FastAPI router、OpenAPI schema、Streamlit page registry 與 worker registry，確認不缺 module。
4. 對動態載入檔採人工明確 allowlist，不因副檔名或目錄整批放行。
5. 每次 entry point、import 或 runtime asset 改變，manifest 必須同步更新；CI 檢查 drift。

| 映像 | 程式 closure 起點 | 特別限制 |
|---|---|---|
| API | `api/`、`domains/`、`subsystems/`、`shared_kernel/`、`infrastructure/`、正式 `line/` module | 只 API 可含 MySQL driver；禁止 UI、測試、migration 與 operator code |
| UI | `ui/` 與 UI typed client 所需的最小共享 schema | 禁止 `infrastructure/`、DB adapter、PyMySQL、可寫資料檔 |
| runtime-ops | 四個正式 scripts 及最小 `subsystems/`、HTTP adapter、`shared_kernel/` closure | 禁止 DB adapter／driver；只呼叫 authenticated Private API |
| ingestion | 未來核准 entry point 的最小 closure | 未完成前 manifest 必須不存在，避免誤建 |

### 2.4 正式 runtime assets

目前 `config/`、`db/`、`validation/` 內的檔案不得直接封裝。真正不可變、執行時必要的 release asset 應先搬到獨立 `runtime_assets/`，逐檔完成 owner、用途、公開性、個資、可變性、保留期限與 SHA-256 審核。

| 現有內容 | 處置 |
|---|---|
| `line/static/*.html` | API 正式靜態頁；逐檔 allowlist 後可移入／封裝 |
| `line/default_menu.jpg`、`line/staff_menu.jpg` | 先做 EXIF／metadata／敏感資訊掃描；核准後作 immutable release asset |
| `db/templates/contracts/*.json`、`*.xlsx` | 不直接封裝；確認為空白模板、去除作者 metadata、掃描個資與外部連結後逐檔核准 |
| `config/message_templates.json` 等可編輯設定 | 搬到 API 擁有的耐久設定儲存；不可變預設值另建已審核 release default |
| `config/liff_settings_history.json` | 歷史資料，永不封裝 |
| `config/rich_menu_ids.json`、根目錄 `rich_menu_ids.json` | provider/runtime state，永不封裝；由受控耐久設定提供 |
| `line/test_result.txt`、`line/LINE_Bot_SOP.md` | 測試／文件，永不封裝 |

現有 `contract_client_copy.xlsx` 的初步唯讀掃描發現作者 metadata 與一筆符合電話格式的內容，目前為「未核准資產」；人工確認與去 metadata 前不得加入 API image。

## 三、各 Dockerfile 詳細規劃

### 3.1 共通基線

所有 Dockerfile 必須：

- 使用 Python 3.11 slim 明確 digest，不使用浮動 `latest`。
- 使用 multi-stage build；編譯器、lock、測試與掃描工具不進 final stage。
- 以 lockfile 安裝獨立 dependency group，不沿用整包開發環境。
- final image 使用固定 UID/GID non-root、唯讀 root filesystem、最小 writable `/tmp`。
- 不安裝 VPN client、shell、git、curl、編譯器、資料庫 CLI；network tunnel 由 VPC／Cloud VPN 提供，不由 container 建立。
- 不使用 `ARG`／`ENV` 注入 secret；secret 僅由 Secret Manager 在部署時掛載／引用。
- 不封裝 NAS private IP、VPN PSK、BGP ASN/address、route、DB password、MySQL client private key、LINE secret 或固定 OIDC token。
- 不把 `.pyc`、`__pycache__`、source map、測試報告或 build cache 複製到 final stage。
- OCI label 只記錄 commit SHA、build time、source repository 與 image revision；不得包含操作者帳號、內部位址或 token。
- 產出 SBOM、dependency vulnerability scan、provenance 與 image signature；未達政策即 fail closed。

### 3.2 `Dockerfile.api`

只封裝 `api.main:app` 的完整 closure 與已核准 runtime assets。此映像是唯一允許包含 MySQL client library 的映像，也是唯一在部署時取得 DB private DNS／IP、DB password、MySQL CA／client cert／private key及 Direct VPC network tag 的資源。

VPN PSK、Cloud Router/BGP 與 tunnel 設定不屬於 application image。MySQL mTLS material只能由 Secret Manager 掛入 memory-backed／唯讀路徑；image layer、build log、OCI label 與 command argument 都不得出現內容。

不得包含 UI、worker、monitor、ingestion、開發通知、migration／schema、可變 JSON history、舊合約／媒體／封存資料。合約封存與 LINE 媒體必須使用 production object-storage adapter；必要設定不存在時 readiness 失敗。

啟動與單 tunnel 驗證：

- import `api.main` 成功，全部 router 掛載且 OpenAPI 可產生。
- 在 disposable 設定下監聽 `PORT` 並通過 process liveness；不接正式 NAS。
- authenticated readiness 檢查 private route、TCP、MySQL mTLS server identity 與最小權限 query；不得由公開 health 暴露拓樸或錯誤細節。
- tunnel／BGP／route 不可用時，liveness 可維持但 readiness 必須 unavailable；DB mutation 回傳 typed retryable unavailable，不得改連 public address。
- tunnel 恢復後重新建立連線池並驗證 server identity、fresh facts 與 lease；不得沿用中斷前 stale connection／result。
- image 中找不到 Streamlit、測試工具、VPN secret、DB migration entry point 與禁止路徑。

### 3.3 `Dockerfile.ui`

只封裝 Streamlit app、頁面、typed API client 與顯示資產。UI 不得包含 MySQL driver、DB credential 名稱、repository／adapter、VPN client、NAS route資訊、`db/` 或可寫業務資料。

啟動前置：所有表單／模板管理已改呼叫 typed API，不再直接 `open()`、`listdir()`、寫入或刪除 repository 內檔案。未達成時 build gate 失敗。

啟動驗證：

- `streamlit run ui/app.py` 監聽 `${PORT}`，`/_stcore/health` 成功。
- page registry 每個正式頁面可 import；缺一頁即失敗。
- 以 mock API 驗證登入、主要頁面及 typed unavailable；VPN／DB 故障只能由 API 狀態呈現，UI 不得自行連 DB。
- package inventory 證明沒有 PyMySQL、DB adapter 或 VPN tooling。

### 3.4 `Dockerfile.runtime-ops`

同一映像提供兩個 immutable command：

1. Worker Pool：正式 supervisor 同時管理 durable-job、LINE-delivery、incident worker，不監聽 `PORT`。
2. Monitor Job：覆寫為 `python -m scripts.run_service_monitor --once`。

worker supervisor 必須具備子程序明確命名、graceful shutdown、SIGTERM 傳遞、restart/backoff 上限、永久失敗時 non-zero exit、不得吞 exception、不得啟動 Knowledge worker。它只能用 Google OIDC 呼叫 Private Operations API，不得包含 DB driver、DB secret、NAS route 或 VPN material。

Monitor Job 使用獨立 Service Account，只取得探測與告警 API 的最小權限；不繼承 worker 的 delivery 權限。雖共用映像，resource、identity、command、env、release gate 與告警必須分離。

啟動驗證：

- 以 mock Private API 啟動 Worker Pool command，三個 worker 都進入 running 並產生可觀測 heartbeat。
- 模擬任一 child crash，確認有限重啟後 supervisor 非零結束；由 Worker Pool replacement policy 接手，不靠 HTTP probe。
- 模擬 API 因 tunnel down 回傳 typed unavailable，worker 必須 bounded backoff，不丟 task、不 busy loop、不假成功。
- `--once` monitor 在正常、VPN／DB 告警、API timeout 三種情況回傳約定 exit code。
- image inventory 證明沒有 Knowledge、file watcher、本機 launcher、PyMySQL、schema、migration 或 VPN tooling。

### 3.5 `Dockerfile.ingestion`

只記錄目標，不先做空殼。須先具備核准的正式 HTTP entry point、格式與大小限制、惡意檔掃描、object storage、durable enqueue、idempotency 與失敗清理契約，才可建立 manifest 與 Dockerfile。

未滿足時，CI 預期結果是 `BLOCKED_NOT_IMPLEMENTED`，不得用 placeholder server 取得綠燈。ingestion 永遠不持有 DB、MySQL mTLS 或 VPN secret。

## 四、機敏、歷史與開發資料排除

### 4.1 Build context 第一層排除

`.dockerignore` 至少排除：

- `.git/`、`.agents/`、`.codex/`、`.venv/`、IDE 設定。
- `.env*`、`*.pem`、`*.key`、`*.p12`、`*.pfx`、service-account JSON、VPN config／PSK、token／credential。
- `history/`、`document/`、`scratch/`、`logs/`、`backups/`、`downloads/`、runtime receipts。
- `tests/`、`validation/`、coverage、pytest cache、fixtures、snapshots、golden data。
- `db/`、`config/`、migration、schema、seed、dump、SQL、CSV、XLSX；核准資產只能從獨立 `runtime_assets/` 逐檔加入。
- `.local_media/`、`.monitor_state/`、`runtime_data/` 與任何本機執行產物。
- `__pycache__/`、`*.pyc`、`*.log`、`test_result.txt`。

`.dockerignore` 只保護 builder context，不能取代 final-image allowlist；兩層都必須通過。

### 4.2 Final image 第二層掃描

- 路徑 denylist：禁入目錄、開發 launcher、Knowledge、file watcher、migration／seed／fixture 都不得命中。
- secret scan：私鑰、JWT、Google service-account、token、DB DSN、LINE secret、VPN PSK、BGP shared secret不得命中。
- 拓樸 scan：NAS private/public IP、地端 gateway IP、BGP address／ASN、內部 DNS 不得以常值寫入 image；允許經批准的非機敏環境變數名稱，不允許實際值。
- 歷史／個資 scan：姓名、電話、email、身分證格式、對話、合約、告警歷史、rich-menu runtime ID 與 provider response 不得命中。
- package inventory：UI／runtime-ops／ingestion 不得有 MySQL driver；所有映像不得有 VPN/Tailscale/ngrok tooling。
- `docker history --no-trunc` 不得顯示 secret、內部 URL 或曾寫入後刪除的資料。

只要命中任一 image layer 就重新建置，不以 final filesystem 已刪除放行。

## 五、完整性與可啟動驗證

驗證在 Dockerfile 完成後於 disposable 環境執行，不接正式 NAS、不使用正式 secret、不修改 VPN／firewall、不寫正式外部服務。

### 5.1 靜態完整性 gate

- runtime manifest 與 image filesystem 雙向 exact match。
- Python `compileall`、import closure、dynamic asset closure 通過。
- API router、UI page、worker registry 的正式清單與實際載入清單 exact match。
- 禁止 import closure 命中 `tests`、`validation`、開發 launcher、migration、Knowledge、operator-only 或 VPN client code。

### 5.2 容器啟動 gate

| 映像／command | 必測結果 |
|---|---|
| API Service | timeout 內監聽 `PORT`；liveness 成功；DB readiness 可獨立 unavailable；SIGTERM 優雅結束 |
| UI Service | timeout 內監聽 `PORT`；`/_stcore/health` 成功；所有正式頁可載入 |
| Worker Pool | 三個 worker running；heartbeat 可觀測；fatal child failure 使 supervisor 非零退出；不要求 `PORT` |
| Monitor Job | 單次執行後結束；成功、告警、timeout 的 exit code 可區分 |
| Ingestion Service | entry point 核准後才測；HTTP readiness、惡意檔與 durable enqueue 全通過 |

每個容器以 non-root、read-only filesystem、受限 `/tmp`、drop capabilities、無 secret 條件啟動。若程式嘗試寫 repository path、建立 VPN tunnel或依賴開發檔案，測試必須失敗。

### 5.3 最小整合與單 tunnel smoke

- UI → mock/authenticated API：登入後主要 query 完成；DB unavailable 顯示 typed error。
- Worker Pool → mock Private Operations API：OIDC audience、timeout、bounded retry、idempotency 正確。
- Monitor → API/UI 探測與告警 API：正常、tunnel／DB 異常、API 不可用皆能結束並留下去敏結果。
- API → disposable MySQL/object storage：只有 API 能連線；MySQL mTLS 驗證 server identity；transaction 內不直接呼叫外部 provider。
- staging tunnel drill：停 tunnel 後 API readiness unavailable、mutation fail closed、worker bounded backoff且無 public 3306；恢復後重新驗證 route、mTLS、fresh facts、lease、backlog replay。

實際 tunnel drill 是部署計畫 gate，不在 Docker build 階段假造。Docker 階段以可替換的 network fault／typed adapter 測試證明 application 行為，部署階段再以 staging tunnel 提供實機證據。

## 六、施工順序

1. **封裝前 live-drift 修復**：移除 UI 本機資料讀寫、遷移可變 LINE 設定與歷史、改用耐久 object storage、移除開發通知、完成 Worker Pool supervisor。若涉及 schema，另立已核准 Work Package 並通過 DB gates；本計畫不授權 DB 變更。
2. **資產分類與去敏**：建立 `runtime_assets/`，逐檔審核與 SHA-256 manifest。
3. **依賴切分**：建立 api、ui、runtime-ops、ingestion（未來）dependency groups，更新 lockfile並檢查直接 import。
4. **先做 runtime-ops**：完成 Worker Pool supervisor、Dockerfile、Worker Pool command 與 monitor Job command 驗證。
5. **再做 API 與 UI**：清除本機可變資料依賴後建置，完成 router/page/startup及 DB unavailable smoke。
6. **最後做 ingestion**：正式 entry point 與安全契約核准後才施工。
7. **發布 gate**：SBOM、弱點、secret／PII／拓樸值、image layer、簽章與 provenance 全通過，才推送 immutable digest。
8. **部署 gate**：Direct VPC network tag、單一 tunnel route、MySQL mTLS、DB isolation、tunnel outage/recovery drill 全通過；Docker image 不承擔建立或修復 VPN。

## 七、計畫驗證結果

本表驗證「計畫是否能機械式阻止不安全或不完整封裝」，不是聲稱目前尚未建立的 container 或 tunnel 已完成測試。

| 驗證項目 | 結果 | 證據／計畫控制 |
|---|---|---|
| 與單一 Cloud VPN 計畫一致 | PASS | Worker Pool/Job/Service 型態、Direct VPC、non-HA tunnel failure semantics 已對齊 |
| 只允許正式程序 | PASS | 第 2.1 節固定 entry point；第 2.2 節 denylist |
| 排除開發階段程序 | PASS | launcher、ngrok、file watcher、Knowledge、`DEV_*`、假 HTTP worker server 均禁止 |
| 封裝程序完整 | PASS | import／asset closure、runtime manifest 雙向 exact match；缺檔即失敗 |
| 程序可正常啟用 | PASS | Service、Worker Pool、Job 分別採正確 startup／exit／health gate |
| 單 tunnel 中斷安全 | PASS | liveness/readiness 分離、typed unavailable、bounded backoff、無公開 3306 fallback |
| 無機敏與拓樸值 | PASS | build-context + final-layer secret／PSK／private key／IP／BGP scan |
| 無歷史／舊資料 | PASS | history、DB/config history、runtime state、舊合約／媒體、validation dataset 禁入 |
| 未完成服務不假裝成功 | PASS | ingestion 明確 `BLOCKED_NOT_IMPLEMENTED`；API/UI live-drift 未修前禁止 production build |
| DB 變更 | PASS（不適用） | 本次無 schema、migration、seed 或既有 DB 操作；後續若需要另走正式 DB gates |

**總結：`PLAN_VALIDATION_PASS`。** v2 已對齊「Direct VPC＋HA VPN gateway resource 上單一 Cloud VPN tunnel」部署方案。連線方案不改變 4 個 image 的核心程式切分，但修正 Worker Pool 啟動模型、API 單 tunnel failure semantics、secret／拓樸資料排除及 tunnel outage/recovery 驗證。實際映像尚未施工；前置條件完成前不得宣稱 API、UI 或 ingestion 已具 production readiness。
