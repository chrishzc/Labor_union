# Cloud Run Dockerfile 正式封裝計畫 (v1 - Superseded)

文件狀態：`superseded`（已被 `document/雲端部署/計劃書/Cloud_Run_Dockerfile封裝計畫_v2.md` 取代）

部署基線：`document/雲端部署/計劃書/單一Cloud VPN計畫書.md`

適用範圍：歷史 5 資源規劃存檔。現行正式標準為 3 個映像、4 個 Cloud Run 資源之 4+1 拓樸。

## 一、摘要與結論

最終規劃為 **4 份 Dockerfile、4 個映像、部署到 5 個 Cloud Run 資源**：

| Dockerfile | 正式映像 | Cloud Run 資源 | 用途 |
|---|---|---|---|
| `docker/Dockerfile.api` | `union-api` | 1 個 Service | 唯一可存取地端 MySQL 的 FastAPI |
| `docker/Dockerfile.ui` | `union-ui` | 1 個 Service | Streamlit 薄 UI，只呼叫 API |
| `docker/Dockerfile.runtime-ops` | `union-runtime-ops` | 1 個 worker Service + 1 個 monitor Job | 三種正式 worker 共用一個映像；monitor 同映像、不同命令 |
| `docker/Dockerfile.ingestion` | `union-ingestion` | 1 個 Service | 未來檔案接收服務；正式 entry point 完成後才可建置 |

「5+1」中的 `+1` 是地端 NAS MySQL，不是容器。共用 `runtime-ops` 映像只共用程式與依賴，不共用執行個體、Service Account、環境變數或擴縮設定。

本次驗證結論：封裝規則本身已可確保正式映像只含正式程式，並可阻止不完整或含機敏／歷史資料的映像進入 Artifact Registry。但目前 live code 尚有下列實作前置條件；未完成前，對應映像必須拒絕建置或不得標記為 production：

1. UI 表單管理仍直接讀寫 `db/form_templates.json` 與 `db/templates/`，不符合薄 UI，也不適用 Cloud Run 暫存檔案系統。須改為 typed API；UI 映像不得攜入這些資料檔。
2. LINE 設定、LIFF 歷史與 rich-menu ID 仍使用可變 `config/*.json`／根目錄 `rich_menu_ids.json`。須移到 API 擁有的耐久儲存，或把真正不可變的 release default 搬到經審核的 `runtime_assets/`。
3. 合約封存、LINE 媒體與 rich-menu 圖片仍存在本機檔案預設路徑。正式環境須改用耐久 object storage adapter，且未設定時 fail closed，不得回退到容器檔案系統。
4. `line/line_bot.py` 的 `DEV_REVIEW_NOTIFY_URL` 開發通知路徑須從正式 runtime closure 移除；只把環境變數留空不足以證明正式映像沒有開發程序。
5. worker Service 需要一個正式 supervisor，在同一執行個體管理 durable-job、LINE-delivery、incident 三個 worker，並監聽 Cloud Run 的 `PORT` 提供 liveness/readiness。現有三支獨立腳本不可直接當 Cloud Run Service command。
6. ingestion 尚無核准且可啟動的正式 entry point，因此 `Dockerfile.ingestion` 只能先保留設計，不得建立空殼或假成功映像。

完成上述前置條件後才進入 Dockerfile 施工。這可避免為了「先包起來」而把資料檔、開發 launcher 或不完整程序帶入 production。

## 二、正式封裝邊界

### 2.1 允許的正式 entry point

| 資源 | 唯一正式啟動命令（計畫值） | 完整啟動條件 |
|---|---|---|
| API Service | `python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT}` | 所有正式 router 可載入；`/health` 成功；只有此資源取得 DB 與 VPN 連線設定 |
| UI Service | `python -m streamlit run ui/app.py --server.address=0.0.0.0 --server.port=${PORT}` | page registry 全部可載入；健康端點成功；沒有 DB driver／DB secret |
| Worker Service | `python -m scripts.run_runtime_worker_pool` | 同時監督 durable、LINE、incident worker；任一必要子程序永久失敗時整體 unhealthy；監聽 `PORT` |
| Monitor Job | `python -m scripts.run_service_monitor --once` | 單次執行有明確 exit code、timeout 與重試界線；不得常駐或自行排程 |
| Ingestion Service | 待正式 entry point 核准後固定 | 必須監聽 `PORT`、完成驗證與 durable enqueue；未核准前禁止建置 |

worker pool 僅包含：

- `scripts/run_durable_job_worker.py`
- `scripts/run_line_worker.py`
- `scripts/run_incident_worker.py`

`scripts/run_service_monitor.py` 雖與 worker 共用映像，但不由 worker supervisor 啟動，只供 Cloud Run Job 覆寫 command 使用。

### 2.2 明確禁止的 entry point 與程序

下列內容不可出現在 final image，也不可由 production command 間接呼叫：

- `scripts/launchers/start_local_development.bat` 及所有本機／ngrok launcher。
- `scripts/file_watcher.py`、開發檔案監看、hot reload、debug server。
- `scripts/run_knowledge_worker.py`；目前 Knowledge runtime 已明確停用。
- DB reset、bootstrap、migration、seed、fixture、fake-data、backfill、export/import、資料修復腳本。
- CI、lint、測試、coverage、benchmark、產生器與一次性 operator script。
- `DEV_*` 開發通知或 reviewer callback 路徑。
- 任何會在 API lifespan 內嵌 worker 的啟動路徑。

### 2.3 內容 allowlist 與 runtime closure

禁止以 `COPY . .` 或整個 repository 複製。每個映像必須有版本化的 `docker/runtime-manifests/<image>.txt`，逐檔列出允許進入 final stage 的檔案；CI 依 manifest 產生內容清單與 SHA-256，未列入或找不到的檔案都使建置失敗。

manifest 必須由下列證據產生及覆核：

1. 從正式 entry point 建立完整 Python import closure。
2. 掃描 `open()`、`Path.read_*`、`FileResponse`、模板／靜態資產查找與動態 import。
3. 載入 FastAPI router、OpenAPI schema、Streamlit page registry 與 worker supervisor，確認不缺 module。
4. 對動態載入檔採人工明確 allowlist，不因副檔名或目錄整批放行。
5. 每次 entry point、import 或 runtime asset 改變，manifest 必須同步更新；CI 檢查 drift。

允許的程式根目錄只是盤點起點，不代表可以整目錄複製：

| 映像 | 程式 closure 起點 | 特別限制 |
|---|---|---|
| API | `api/`、`domains/`、`subsystems/`、`shared_kernel/`、`infrastructure/`、正式 `line/` module | 只 API 可含 MySQL driver；禁止 UI、測試、migration 與 operator code |
| UI | `ui/` 與 UI typed client 所需的最小共享 schema | 禁止 `infrastructure/`、DB adapter、PyMySQL、可寫資料檔 |
| runtime-ops | 四個正式 scripts 及其最小 `subsystems/`、`infrastructure/http`、`shared_kernel/` closure | 禁止 DB adapter與 DB driver；worker 只能呼叫 authenticated Private API |
| ingestion | 未來核准 entry point 的最小 closure | 未完成前 manifest 必須不存在，避免誤建 |

### 2.4 正式 runtime assets

目前 `config/`、`db/`、`validation/` 內的檔案不得直接封裝。真正不可變、執行時必要的 release asset 應先搬到獨立 `runtime_assets/`，並逐檔完成 owner、用途、是否可公開、是否含個資、是否可變、保留期限與 SHA-256 審核。

候選資產及處置：

| 現有內容 | 處置 |
|---|---|
| `line/static/*.html` | 是 API 的正式靜態頁；逐檔 allowlist 後可移入／封裝 |
| `line/default_menu.jpg`、`line/staff_menu.jpg` | 先做 EXIF／metadata／隱寫與敏感資訊掃描；核准後作 immutable release asset |
| `db/templates/contracts/*.json`、`*.xlsx` | 不得直接封裝；須確認是空白模板而非歷史資料，移除作者 metadata，掃描個資與公式外部連結後逐檔核准 |
| `config/message_templates.json` 等可編輯設定 | 搬到 API 擁有的耐久設定儲存；若有不可變預設值，另建立已審核的 release default |
| `config/liff_settings_history.json` | 歷史資料，永不封裝 |
| `config/rich_menu_ids.json`、根目錄 `rich_menu_ids.json` | provider/runtime state，永不封裝；由 Secret Manager 或耐久設定儲存提供 |
| `line/test_result.txt`、`line/LINE_Bot_SOP.md` | 測試／文件，永不封裝 |

現有 `contract_client_copy.xlsx` 的初步唯讀掃描發現作者 metadata 與一筆符合電話格式的內容，因此目前狀態為「未核准資產」；在人工確認其為合法空白範本內容並完成去 metadata 前，不得加入 API image。

## 三、各 Dockerfile 詳細規劃

### 3.1 共通基線

所有 Dockerfile 必須：

- 使用 Python 3.11 slim 的明確 digest，不使用浮動 `latest`。
- 使用 multi-stage build；編譯器、lock 工具、測試工具只留在 builder，不進 final stage。
- 以 lockfile 安裝；每個映像使用獨立 dependency group，不能沿用整包開發環境。
- final image 使用固定 UID/GID 的 non-root 使用者、唯讀 root filesystem、最小 writable `/tmp`。
- 不安裝 shell、git、curl、編譯器、資料庫 CLI 或套件管理工具；若 base image 無法移除，至少不得作 production entry point 依賴。
- 不使用 `ARG`／`ENV` 注入 secret；secret 僅在部署時由 Secret Manager 掛入環境或檔案。
- 不把 `.pyc`、`__pycache__`、source map、測試報告或 build cache 複製到 final stage。
- 以 OCI label 記錄 commit SHA、build time、source repository 與 image revision；不得寫入操作者帳號或內部 token。
- 產出 SBOM、dependency vulnerability scan 與 image signature；critical/high 弱點依核准政策 fail closed。

### 3.2 `Dockerfile.api`

只封裝 `api.main:app` 的完整 closure 與已核准 runtime assets。此映像是唯一允許包含 MySQL client library 的映像，也是唯一取得 DB endpoint、DB mTLS material 與 VPC/VPN route 的 Cloud Run 資源。

不得包含：UI、worker entry point、monitor、ingestion、開發通知、migration／schema、可變 JSON history、舊合約／媒體／封存資料。合約封存與 LINE 媒體必須使用 production object-storage adapter；若必要設定不存在，startup readiness 必須失敗。

啟動驗證：

- image import `api.main` 成功，全部 router 可掛載且 OpenAPI 可產生。
- 在不連正式 DB 的 disposable 設定下啟動並通過 `/health`。
- DB 不可用時回報明確 degraded/unready，不得啟動內嵌 worker或寫入本機檔案作替代。
- 容器中找不到 Streamlit、測試工具、DB migration entry point 與禁止路徑。

### 3.3 `Dockerfile.ui`

只封裝 Streamlit app、頁面、typed API client 與顯示所需資產。UI 不得包含 MySQL driver、DB credential 名稱、repository／adapter、`db/` 或可寫業務資料。

啟動前置：所有表單／模板管理已改呼叫 typed API，不再 `open()`、`listdir()`、寫入或刪除 repository 內檔案。未達成時 UI image build gate 必須失敗。

啟動驗證：

- `streamlit run ui/app.py` 監聽 `${PORT}`，`/_stcore/health` 成功。
- page registry 的每一個正式頁面可 import；缺一頁即失敗，不允許只驗首頁。
- 以 mock API 驗證登入、主要頁面導覽及 typed error；不得用地端 DB 補齊流程。
- image package inventory 證明沒有 PyMySQL 或 DB adapter。

### 3.4 `Dockerfile.runtime-ops`

同一映像提供兩種 immutable command：

1. Worker Service：正式 supervisor 同時管理 durable-job、LINE-delivery、incident worker，並提供 `/healthz`、`/readyz`。
2. Monitor Job：覆寫為 `python -m scripts.run_service_monitor --once`。

worker supervisor 必須具備：子程序明確命名、graceful shutdown、SIGTERM 傳遞、restart/backoff 上限、永久失敗轉 unhealthy、不得吞 exception、不得啟動 Knowledge worker。它只能用 Google OIDC 呼叫 Private Operations API；不得含 DB driver或取得 DB secret。

Monitor Job 必須使用獨立 Service Account，只取得探測與告警 API 的最小權限；不繼承 worker 的 LINE／delivery 權限。雖共用映像，部署設定與 secret 必須分離。

啟動驗證：

- 以 mock Private API 啟動 worker Service，三個正式 worker 都產生 heartbeat/readiness。
- 模擬任一 child crash，確認有限重啟後服務 unhealthy，Cloud Run 可替換 instance。
- `--once` monitor 在成功／告警／timeout 三種情況回傳約定 exit code。
- image inventory 證明沒有 Knowledge、file watcher、本機 launcher、PyMySQL、schema 或 migration。

### 3.5 `Dockerfile.ingestion`

只記錄目標，不先做空殼。必須先具備核准的正式 HTTP entry point、驗證格式、大小限制、惡意檔掃描、object storage 落點、durable enqueue、idempotency 與失敗清理契約，才可建立 manifest 與 Dockerfile。

未滿足上述條件時，CI 對 ingestion 的預期結果是 `BLOCKED_NOT_IMPLEMENTED`，不是用 placeholder server 取得綠燈。

## 四、機敏、歷史與開發資料排除

### 4.1 Build context 第一層排除

`.dockerignore` 至少排除：

- `.git/`、`.agents/`、`.codex/`、`.venv/`、IDE 設定。
- `.env*`、`*.pem`、`*.key`、`*.p12`、`*.pfx`、service-account JSON、token／credential 檔。
- `history/`、`document/`、`scratch/`、`logs/`、`backups/`、`downloads/`、runtime receipts。
- `tests/`、`validation/`、coverage、pytest cache、fixtures、snapshots、golden data。
- `db/`、`config/`、migration、schema、seed、dump、SQL、CSV、XLSX；核准資產只能從獨立 `runtime_assets/` 逐檔加入。
- `.local_media/`、`.monitor_state/`、`runtime_data/` 與任何本機執行產物。
- `__pycache__/`、`*.pyc`、`*.log`、`test_result.txt`。

`.dockerignore` 只保護送入 builder 的內容，不能取代 final-image allowlist；兩層檢查都必須通過。

### 4.2 Final image 第二層掃描

CI 必須把 final image export 成唯讀檔案清單並執行：

- 路徑 denylist：上述禁入目錄、開發 launcher、Knowledge、file watcher、migration／seed／fixture 都不得命中。
- secret scan：私鑰、JWT、Google service-account 欄位、常見 token、DB DSN、LINE secret、固定帳密不得命中；只允許文件化的測試假值，且正式映像原則上不需要假 secret。
- 歷史／個資 scan：姓名、電話、email、身分證格式、對話、合約、告警歷史、rich-menu runtime ID 與 provider response 不得命中。
- package inventory：各映像只能包含其 dependency group；UI／runtime-ops 不得出現 MySQL driver。
- image history：`docker history --no-trunc` 不得顯示 secret、內部 URL 或被刪除但曾寫入上一層的資料。

掃描命中不得以「檔案最後已刪除」放行；只要存在於任一 image layer 就重新建置。

## 五、完整性與可啟動驗證

驗證須在 Dockerfile 完成後於 disposable 環境執行，不接正式 NAS、不使用正式 secret、不寫正式外部服務。

### 5.1 靜態完整性 gate

- runtime manifest 與實際 image filesystem 雙向比對：無未列入檔案，也無 manifest 缺檔。
- Python `compileall`、import closure、dynamic asset closure 全部通過。
- API router、UI page、worker registry 的正式清單與實際載入清單 exact match。
- 禁止 import closure 命中 `tests`、`validation`、開發 launcher、DB migration、Knowledge 或 operator-only code。

### 5.2 容器啟動 gate

| 映像／command | 必測結果 |
|---|---|
| API | 在 timeout 內監聽 `PORT`；`/health` 成功；SIGTERM 優雅結束 |
| UI | 在 timeout 內監聽 `PORT`；`/_stcore/health` 成功；所有正式頁可載入 |
| Worker Service | 三個 worker ready；`/readyz` 成功；子程序故障與 shutdown 行為符合契約 |
| Monitor Job | 單次執行後結束；成功、告警、timeout 的 exit code 可區分 |
| Ingestion | entry point 核准後才測；HTTP readiness、惡意檔與 durable enqueue 全通過 |

每個容器另以 non-root、read-only filesystem、受限 `/tmp`、drop capabilities、無 secret 的條件啟動。若程式嘗試寫 repository path 或依賴開發檔案，測試必須失敗。

### 5.3 最小整合 smoke

- UI → mock/authenticated API：登入後頁面與主要 query 能完成。
- worker → mock Private Operations API：OIDC audience、timeout、retry、idempotency header 正確。
- monitor → API/UI 探測與告警 API：正常、異常與 API 不可用皆能結束並留下去敏結果。
- API → disposable MySQL／object storage adapter：只有 API 能取得連線；transaction 內不直接呼叫外部 provider。

## 六、施工順序

1. **封裝前 live-drift 修復**：移除 UI 本機資料讀寫、遷移可變 LINE 設定與歷史、改用耐久 object storage、移除開發通知路徑、完成 worker supervisor。若涉及 schema，須另立已核准 Work Package 並通過專案 DB change gates；本計畫不授權 DB 變更。
2. **資產分類與去敏**：建立 `runtime_assets/`，逐檔審核與 SHA-256 manifest；未分類檔案維持禁入。
3. **依賴切分**：建立 api、ui、runtime-ops、ingestion（未來）dependency groups，更新 lockfile並檢查直接 import。
4. **先做 runtime-ops**：其 DB／資料檔邊界最小；完成 supervisor、Dockerfile、worker Service 與 monitor Job 兩種 command 驗證。
5. **再做 API 與 UI**：只有在本機可變資料依賴清除後建置，執行完整 router/page/startup smoke。
6. **最後做 ingestion**：正式 entry point 與安全契約核准後才施工。
7. **發布 gate**：SBOM、弱點、secret／PII、image layer、簽章與 provenance 全通過，才推送 immutable digest；部署只引用 digest，不引用 mutable tag。

## 七、計畫驗證結果

本表驗證的是「計畫是否能在施工時機械式阻止不安全或不完整封裝」，不是聲稱目前尚未建立的容器已完成 runtime 測試。

| 驗證項目 | 結果 | 證據／計畫控制 |
|---|---|---|
| 只允許正式程序 | PASS | 第 2.1 節固定 entry point；第 2.2 節明確 denylist |
| 排除開發階段程序 | PASS | 開發 launcher、ngrok、file watcher、Knowledge、`DEV_*` 均禁止進 final image |
| 封裝程序完整 | PASS | 第 2.3 節 import／asset closure、runtime manifest 雙向 exact-match；缺檔即失敗 |
| 程序可正常啟用服務 | PASS | 第 5.2 節逐資源 startup／health／shutdown gate；未通過不得發布 |
| 無機敏資料 | PASS | build-context + final-layer 兩層 secret／PII scan，未分類資產 fail closed |
| 無歷史／舊資料 | PASS | `history`、DB/config history、runtime state、舊合約／媒體、validation dataset 全面禁入 |
| 未完成服務不會假裝成功 | PASS | ingestion 明確 `BLOCKED_NOT_IMPLEMENTED`；API/UI live-drift 未修復前禁止 production build |
| DB 變更 | PASS（不適用） | 本次無 schema、migration、seed 或既有 DB 操作；若後續需要，另走正式 DB gates |

**總結：`PLAN_VALIDATION_PASS`。** 這份計畫已把「只含正式程序、內容完整、能正常啟動、無機敏與歷史資料」轉成可驗證且 fail-closed 的建置／發布門檻。實際映像尚未施工，因此 container build 與 runtime smoke 應在下一階段依本計畫執行；在第六節前置條件完成前，不得宣稱 API、UI 或 ingestion 已具 production readiness。
