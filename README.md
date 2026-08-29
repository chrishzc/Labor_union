# 新竹市月子照顧服務人員職業工會－行政流程系統

此專案提供 LINE 整合、案件與月嫂排班、訂單生命週期、客戶帳務、薪資、月嫂應付、
銀行流水匯入與政府補助的地端行政系統。管理端是 React；正式業務操作透過 FastAPI、
application workflow 與 MySQL 完成。

「架構重整」分支已完成架構重整與遺留退役治理，正作為取代 `main` 的 release candidate。
系統以 `Global → Domain → Subsystem → Module` 分層，
並以明確的根事實、typed command、Preview／Apply、outer Unit of Work、receipt 與 outbox
維持可重播、可稽核的業務操作。版本與驗收狀態以 Git、release manifest 及架構文件內的
evidence 為準；不要以本 README 的文字代替實際驗收。

> **Current governance checkpoint（2026-08-29）**：Task 97 final-candidate discovery 的 entry queue 為
> 685 entries，其中 437 `active`、74 `operator_only`、22 `retired_410`、152 legacy `review_required`，
> generic placeholder 已為 0。逐列 Task 97 disposition 為 437 `active_canonical`、74
> `operator_only_guarded`、22 `retired_410`、147 `blocked_external_evidence`、5
> `rewrite_to_canonical`；152 張 terminal receipt 的結果仍是 `blocked`，不是完成。下方 2026-08-10
> 的 348／0 數字是該次 release candidate 的歷史 snapshot，不代表 current repository 已通過 Task 97。
> Current conclusion 為 `ARCHITECTURE_COMPLIANCE_NOT_CONFIRMED`，詳見
> [任務 97](document/架構重整/02_決策與退役執行記錄/97_架構一致性修復與全域驗收計畫.md#13-2026-08-29-current-execution-checkpoint)。
> 2026-08-29 最新人工優先序：其他任務與本機當前 Task 97 發生重疊衝突時，
> 以 Task 97 優先並停止重疊 lane。

## 2026-08-10 歷史 Release Candidate 摘要

以下為 2026-08-10 當時的候選版本摘要，不代表目前 release 狀態：

- LINE runtime：保留 webhook、身分綁定與人工 review、訊息設定、Rich Menu、媒體、
  order group、delivery task、matching notification、runtime health 與正式 worker 啟動流程。
- Knowledge Retrieval：提供索引、知識項目、publication/review、重試工作與問答的 typed API、
  管理 UI、worker 與 MySQL runtime schema。
- Internal Access：所有已登入且 enabled 的內部使用者具有相同業務功能權限；保留登入驗證、
  操作人員身分、session 與安全稽核，不使用 role／capability 差異限制業務功能。
- Anomalies／Finance Import：IMPORT-004 可安全補送遺漏告警；IMPORT-006 只寫 canonical
  `anomaly_current_alerts`，歷史補投影使用單調 outbox event version，不再常駐掃描全歷史批次。
- Scheduling UI：異常中心提供 typed 服務人員月曆 deep link；配對中心採單一分支渲染、
  一次性 navigation token，並保留智慧配對實際流程。
- Schema release：candidate schema 已收斂至 part 165 與 migration release v9；BreezySign、
  舊 Contract API、舊 alert authority 及其他已裁決 legacy boundaries 不再是正式入口。
- 治理：348 個 API／CLI／UI entry 已全部裁決，結果為 306 `active`、41 `operator_only`、
  1 `retired_410`、0 `review_required`；九份業務附件已依目前 hash 完成人工語意裁決。

本機隔離 candidate 當時完成兩次 bootstrap、restart/read-smoke 與退役結構不存在驗證；
這不代表已授權套用到任何其他部署環境。原始 receipt 已自目前工作樹移除，必要時從 Git
歷史精準取回；版本摘要見 [`CHANGELOG.md`](CHANGELOG.md)。

## 2026-08-13 開發者 DB、月嫂配對與啟動入口更新

本次修正開發者更新 `main` 後，程式與本機 MySQL schema 不同步所造成的 API 500、runtime
heartbeat／outbox worker 缺表問題。新增保留資料的 candidate upgrade workflow，並將所有專案
operator-facing launcher 集中到 [`scripts/launchers/`](scripts/launchers/)。完整變更與已知限制見
[`CHANGELOG.md`](CHANGELOG.md#2026-08-13--開發者本機資料庫維護與啟動腳本收斂)。

此版本也加入月嫂配對偏好、長假／暫停接案的 typed API 與管理 UI；配對中心與 Calendar 讀取同一
份 current facts。資料庫升級會納入 release 188 的新增欄位與資料表。HCM 日常匯入收斂至受驗證的
Web upload；BeClass scripts 僅保留為受控的 historical import，不再是一般 Web／File Watcher
寫入入口。

更新程式後先執行唯讀檢查；確認 ready 後，再停止 API、UI、monitor、workers 並執行實際 DB
更新：

```powershell
.\scripts\launchers\start_local_development.bat --dry-run
.\scripts\launchers\update_local_database.bat --dry-run
.\scripts\launchers\update_local_database.bat
.\scripts\launchers\start_local_development.bat --smoke-test
```

若本機未安裝 `mysql`／`mysqldump`，更新工具會在 Compose 預設的 `mysql_db` 正在執行時
自動使用容器內的 MySQL CLI。若開發者使用不同容器名稱，請在個人的 `.env` 設定
`MYSQL_CONTAINER=<docker ps 顯示的容器名稱>`；請勿提交個人 `.env`。

Windows smoke 只啟動並檢查 API 與 React/Vite，驗收固定為 GET-only，結束時只終止
本次建立的應用程序。一般 launcher 則在完整 DB current gate 通過後啟動 FastAPI 8000、React/Vite
5173、runtime monitor、durable job worker 與 incident worker；LINE credentials 缺失時只略過 LINE
worker。兩種模式都不啟動 Streamlit 或通用 File Watcher，日常檔案匯入以 Web UI 上傳為正式入口。

需要捨棄資料並建立 current canonical schema 的空白 DB 時使用 `scripts/launchers/reset_DB.bat`；它不載入
業務 fixture，只保留 canonical schema artifacts 明列的 system seed。

## 給開發者與 Agent 的開始方式

1. 先讀 [`AGENTS.md`](AGENTS.md)：工作區、dirty worktree、測試與 Git 規則。
2. 讀 [`document/架構重整/00_開發者與Agent導覽.md`](document/架構重整/00_開發者與Agent導覽.md)：程式定位與修改邊界。
3. 讀 [`00_Global_共同契約.md`](document/架構重整/01_規格基線/00_Global_共同契約.md) 與對應 Domain 規格。
4. 查閱對應 Work Package／evidence，再檢查 live schema、route、workflow、repository 與測試是否有漂移。

`system_map*.md`、`system_map*.yaml`、ADAD 記錄與歷史文件僅供追溯，**不是** SSOT、授權或實作 gate。

## 架構速覽

```mermaid
flowchart LR
  UI["React\n管理端 UI"] --> API["FastAPI\nTyped API / Webhook"]
  INPUT["LINE / 檔案 / 外部平台"] --> API
  API --> APP["Subsystem workflow\n唯一 outer Unit of Work"]
  WORKER["Inbox / Outbox / Durable Job Worker"] --> APP
  APP --> DOMAIN["Domain\n根事實與業務規則"]
  DOMAIN --> PORT["Typed ports"] --> INFRA["MySQL / 外部 adapters"]
  INFRA --> DB[(MySQL)]
  APP --> RECEIPT["receipt / outbox / durable job"] --> WORKER
```

核心規則：

- Query 唯讀；Preview 零寫入；Apply 重新讀取最新鎖定的根事實後才提交。
- 一個業務命令只有一個 outer Unit of Work owner；repository 與 adapter 不可自行 commit。
- 同一命令以 correlation、fingerprint、idempotency 與 receipt 支援安全重播。
- UI、route、webhook、file watcher 與外部平台不得直接改寫 Domain 根事實。
- 外部副作用只可由已提交的 outbox、inbox 或 durable job worker 執行。

## 專案地圖

```text
api/                 FastAPI routes、dependencies、Pydantic schemas
ui_react/            React 管理端與 bounded typed API clients；不放業務規則
ui/                  Legacy Streamlit rollback 頁面；標準本機 launcher 不啟動
domains/             Domain 根事實、狀態機與 business rules
subsystems/          Preview／Apply workflow、跨 Domain 協調、query models、workers
infrastructure/      MySQL 與外部 provider 的 typed-port 實作
shared_kernel/       共用 command、durable job、typed error 等 Global primitives
db/schema_parts/     依序套用的 additive schema parts
db/migration_releases/  release manifest 與 migration descriptors
scripts/             匯入、migration、維運 helper 與 worker process modules
scripts/launchers/   開發者／維運人員直接執行的本機入口與 dry-run 說明
line/                LINE adapter、Webhook 和執行程序
tests/               Module、Subsystem、Domain、Global 層級驗證
fixtures/            經核准的版本化測試資產；不得直接復活退役 fixture 或套用至正式資料
document/架構重整/  正式規格、決策／退役記錄、追蹤清單與 evidence
```

### Domain 對照

| Domain | 主要位置 | 責任摘要 |
|---|---|---|
| Orders | `domains/orders/`、`subsystems/orders/` | 條款、服務開始／完成、取消、reopen 與 lifecycle |
| Assignments／Scheduling | `domains/scheduling/`、`subsystems/scheduling/` | assignment generation、服務日、檔期、請假與代班 |
| Payroll | `domains/payroll/`、`subsystems/payroll/` | assignment-owned 薪資義務與調整 |
| Client Finance | `domains/client_finance/`、`subsystems/client_finance/` | 客戶應收、收款、退款、沖正、調整與核銷 |
| Staff Payables | `domains/staff_payables/`、`subsystems/staff_payables/` | 月嫂應付、出款與退匯／沖正 |
| Finance Import | `domains/finance_import/`、`subsystems/finance_import/` | 銀行來源事實、分類與委派至 owning Domain |
| Government Subsidy | `domains/government_subsidy/`、`subsystems/government_subsidy/` | 補助申請、核准、撥款、allocation 與 reversal |
| Anomalies | `domains/anomalies/`、`subsystems/anomalies/` | 異常 projection、告警與人工處理進度 |
| Case Import | `domains/case_import/`、`subsystems/case_import/` | BeClass／HCM 驗證、review 與 case bootstrap |
| Access／LINE／Jobs | `subsystems/access/`、`subsystems/line/`、`subsystems/jobs/` | 內部登入、actor／audit、webhook／delivery、durable worker |

完整 ownership、SSOT、狀態機與跨域不變量請以
[`15_正式規格索引與裁決總表.md`](document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md)
及各 Domain 規格為準。尚在規劃、待授權及已封存功能計畫的路由見
[`document/功能開發計畫/README.md`](document/功能開發計畫/README.md)。

## 本機開發

### 必要設定

建立本機 `.env`（已被 Git 忽略）。至少設定：

```env
APP_ENV=development
# 只能四選一：local_bypass、local_auth、local_developer_session、production。缺漏時 fail closed。
ACCESS_CONTROL_PROFILE=local_bypass
ENABLE_ADMIN_AUTH=false
# local_auth／production 必須為 true，並設定 versioned Fernet keyring；不得提交真實 key。
# ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION=v1
# ACCESS_CONTROL_TOTP_KEYRING=v1:<Fernet-base64-key>
# 手動分別啟動 API／Worker 時，各 process 必須共用；用 launcher 時會自動產生且不寫檔。
INTERNAL_SERVICE_SHARED_KEY=<至少 32 字元的本機專用隨機字串>
INTERNAL_API_BASE_URL=http://127.0.0.1:8000
```

`local_bypass` 只適用於 development／dev／local／test，且必須同時設定
`ENABLE_ADMIN_AUTH=false`；`local_auth` 必須設定 `ENABLE_ADMIN_AUTH=true`，走帳密＋TOTP 的完整流程。
`local_developer_session` 同樣只適用於 development／dev／local／test 且必須啟用 auth；它讀取本機
ignored `.env` 的 `DEV_ROOT_USERNAME`／`DEV_ROOT_PASSWORD` 來驗證唯一 root 的密碼、建立真正 Bearer
Session 與 audit，但暫時不要求 TOTP，僅供本機開發驗證其他 Access Control 邊界。
production 固定啟用管理員 Session 與 TOTP，不存在 `LEGACY_SHARED_KEY` 或 `X-Legacy-Shared-Key` 的
human authorization fallback。`INTERNAL_SERVICE_SHARED_KEY` 只供本機 machine caller 使用；production
machine caller 使用 Google-signed OIDC。不得將 `.env`、token、私鑰或正式資料提交至 Git。

### root bootstrap 與 MFA key rotation

首次建立唯一 root 前，先以唯讀計畫確認目前資料庫是預期的 `lu_test_*` 目標；不得對
`union_db` 執行此流程。root 帳密只在受保護的互動終端輸入，不得寫入命令列、文件或 receipt：

```powershell
.\.venv\Scripts\python.exe -m scripts.update_local_database --mysql-container mysql_db
.\.venv\Scripts\python.exe scripts\create_admin.py --bootstrap-root
```

成功後，將 root 帳號名稱與密碼以 ignored `.env` 的 `DEV_ROOT_USERNAME`／`DEV_ROOT_PASSWORD`
設定，僅供 `local_developer_session` 產生真實 Bearer Session；不要在 `local_auth` 或
`production` 以此略過 TOTP。首次一般登入會回 MFA enrollment challenge，使用者掃描畫面上以一次性
provisioning URI 在本機記憶體產生的 QR code（或展開手動設定資訊）、完成第一組 TOTP，再安全保存只顯示一次的 recovery codes。

TOTP keyring 由部署／維運擁有，資料庫只保存 ciphertext 與 key version。rotation 時先把新
Fernet key 加入 `ACCESS_CONTROL_TOTP_KEYRING`、切換 `ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION`、
重啟所有 API/worker 並以既有 factor 驗證登入；待所有舊 ciphertext 已透過受控 re-encryption
程序更新且保留回復金鑰後，才可移除舊 key。任一步失敗要保留舊 key、停止 MFA mutations、保留
security audit，不能以關閉 MFA 或重用 legacy human key 作回復。

### 啟動服務

先確認 Docker 與 MySQL 狀態，再視需求分別啟動服務：

```powershell
docker compose up -d

# FastAPI
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload

# Streamlit
.\.venv\Scripts\python.exe -m streamlit run ui/app.py

# Durable Job Worker
.\.venv\Scripts\python.exe scripts/run_durable_job_worker.py

# Incident／anomaly／audit-retention Worker
.\.venv\Scripts\python.exe scripts/run_incident_worker.py

# Runtime Monitor
.\.venv\Scripts\python.exe scripts/run_service_monitor.py
```

Worker 與 Monitor 都只呼叫 authenticated Private Operations API；啟動後會主動移除從父 process
繼承的 DB credential。MySQL 連線只存在 FastAPI process。Private endpoints 不列入 OpenAPI。
local/test 使用至少 32 字元 shared key；production 固定使用 Google-signed OIDC ID token，並精確
驗證 Private API audience、caller service name 與 service-account allowlist，不接受 shared-key fallback。
Worker 會上報自身 instance／PID／hostname／release，API 不會用自己的 process identity 冒充 Worker。
獨立手動啟動的 Worker／Monitor 會以 process environment 優先、再讀取 Git-ignored `.env` 的方式取得此 key；
API 與所有 Worker 必須重啟後才會使用更新值。

Cloud Run 環境至少設定：

```env
APP_ENV=production
INTERNAL_SERVICE_AUTH_MODE=google_oidc
INTERNAL_API_BASE_URL=https://<private-api-service-url>
INTERNAL_SERVICE_OIDC_AUDIENCE=https://<private-api-service-url>
INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS=durable-job-worker=<durable-sa>,incident-worker=<incident-sa>,line-worker=<line-sa>,runtime-monitor=<monitor-sa>
INTERNAL_API_MAX_ATTEMPTS=3
```

各 caller service account 仍須由部署者只授予目標 Private API 的 Cloud Run Invoker；本輪只交付程式
契約，不建立 IAM、Cloud Run、網路、Dockerfile 或 image。

雲端部署尚未獲得執行授權。Cloud Run、單一 Cloud VPN 與 Dockerfile 的設計、成本假設、
網路邊界與驗收前置條件，集中於
[`document/雲端部署/計劃書/`](document/雲端部署/計劃書/)；這些都是規劃文件，不代表已建立
Google Cloud 資源、已部署映像或已開放任何網路路徑。

[`scripts/launchers/start_local_development.bat`](scripts/launchers/start_local_development.bat) 與
[`scripts/launchers/start_local_development.sh`](scripts/launchers/start_local_development.sh) 是 Windows／Unix
本機開發啟動入口。它們先驗證完整 DB release chain 已到 current，再啟動 FastAPI 8000、React/Vite
5173、runtime monitor、durable job worker 與 incident worker；LINE credentials 缺失時只顯示 skip，
不會阻擋必要服務。launcher 不啟動 Streamlit 或通用 File Watcher，也不會自動套用資料庫 schema。
Unix 免登入開發可使用
[`start_local_development_no_auth.sh`](scripts/launchers/start_local_development_no_auth.sh)，它只設定
development `local_bypass` 後委派同一標準入口。所有 operator-facing 腳本、用途與退役對照見
[`scripts/launchers/README.md`](scripts/launchers/README.md)。Durable Job Worker 主機 supervision 目前依
人工裁決暫緩；只保留既有排程任務的 recovery 查詢與解除安裝：

```powershell
.\scripts\launchers\get_durable_job_worker_task_status.ps1
.\scripts\launchers\uninstall_durable_job_worker_task.ps1 -WhatIf
```

## 資料庫與資料安全

- Schema 調整先新增 `db/schema_parts/`，再同步 `db/schema.sql` 與對應的 migration release metadata。
- 保留資料升級、cutover、回復與目標主機操作必須依 Work Package／runbook 執行，不可自行套用 migration。
- `scripts/launchers/start_local_development.bat` 不初始化、不重建也不假資料化資料庫；它只用於本機開發，禁止當作正式部署入口。
- `fixtures/` 只允許版本化、去敏且經核准的測試資產；目前舊 `db_snapshot_v2/v3` 已退役且尚未重建，不得從歷史版本直接復活或用於正式資料庫。
- 銀行檔、LINE webhook、BeClass／HCM 與其他外部輸入先進 inbox／import workflow，再由 owning Domain 寫入正式事實。

開發者更新 `main` 後，若要保留現有資料，執行
`scripts/launchers/update_local_database.bat`。預設 fast path 會先依當機 `.env` 回讀本機
development source，建立綁定該 DB、server、release 與 baseline schema 的完整 dump／receipt。
runner 會從 canonical manifests 動態解析 baseline 到 current latest 的完整 ordered chain，逐支確認
qualification 後依序套用 schema-only additive releases；每一步 DDL 前後都會驗證代表性舊資料指紋。
共享 qualification 只證明 release、SQL、descriptor 與 evidence table scope，不會把其他開發機
綁到製作 receipt 時的 DB 名稱、host、port 或資料內容。資料庫名稱可由各機器自行設定，但遠端、
production profile 與 MySQL 系統 schema 一律 fail closed。長時間 candidate replacement 只有明確
使用 `--strategy replacement --allow-long-run` 才會執行。
若 MySQL 在預設 Docker Compose 的 `mysql_db`，工具會自動使用容器中的 MySQL CLI；自訂容器名時
才需要於 `.env` 覆寫 `MYSQL_CONTAINER`，不需要每位開發者在 Windows 安裝額外的 client。
若舊版曾建立 competing Knowledge schema，工具只在九張 Knowledge owned tables 全部為空、
metadata fingerprint 完整相符且沒有外部 inbound FK 時，於 candidate 重建 canonical 148／163；
任一資料列或未知 drift 都會在唯讀 plan 階段阻擋，禁止自動猜測轉換。
Migration descriptor 對 parent table 只擁有自己明列的新欄位與物件，不獨占 parent table 原有
metadata；後續正式 release 加入同一 owned table 的 object，必須以精確 successor 契約與回歸測試
辨識，不能讓較早 artifact 被誤判 drift，也不能用寬鬆名稱比對放過錯誤契約。
每一支 release 的 qualification receipt 必須綁定該 release fingerprint；整條 release chain 的 aggregate
fingerprint 只表示 bundle 身分，不能取代逐 release qualification。Fast additive journal 以
`source_database + release_id` 分鏈；同一來源已完成的 release journal 會保留，runner 只從目前
連續 exact prefix 的下一支續跑。若 journal 已開始但原本的 machine-local dump／receipt 遺失，runner
必須停止並要求人工 recovery，不得重做新備份冒充原始 baseline。

若要捨棄現有資料並建立版本庫 current canonical schema 的空白資料庫，執行
`scripts/launchers/reset_DB.bat`。它會先驗證 base schema、current schema assembly、ordered artifact hashes
與 validation manifest；預檢成功且使用者輸入 `RESET` 後，才刪除 `union_db` 並建立 current schema。
它不載入業務 fixture，且不是保留資料更新的相容別名；canonical schema artifacts 正式聲明的 system
seed 仍會建立。

執行前必須停止 API、UI、monitor 與 workers，完成後再重啟。兩個入口都只供本機開發，禁止用於
production／shared staging；任何 partial／drift 都會停止，不會猜測修復，candidate 與 receipts
會保留在 `scratch/local_database_updates/` 供診斷。

## 驗證

使用專案虛擬環境；先跑受影響範圍，再依 Module → Subsystem → Domain → Global 擴大：

```powershell
# 單一測試檔
.\.venv\Scripts\python.exe -m pytest tests/test_order_auto_completion_workflow.py

# 指定測試案例
.\.venv\Scripts\python.exe -m pytest tests/test_order_auto_completion_workflow.py -k stale

# 完整 release candidate 測試
.\.venv\Scripts\python.exe -m pytest -q

# 提交前格式檢查
git diff --check
```

2026-08-10 release candidate 的完整測試結果為 `1488 passed, 61 skipped`；skip 項目是依環境、
外部服務或明確退役流程隔離的測試，不可將此數字直接套用到未授權的部署環境。

需要 MySQL 的 integration／E2E 測試只能使用明確設定的 disposable 資料庫；不要將測試、candidate、
fixture 或 production database 混用。

## 文件導航與權威順序

1. 人工最新明確裁決。
2. [`document/架構重整/01_規格基線/`](document/架構重整/01_規格基線/) 中已確認的正式規格與裁決。
3. 既有業務規格、狀態機與欄位權威文件，作為追溯來源。
4. live schema、production code、API、SQL writer 與 production caller，作為現況證據。
5. [`02_決策與退役執行記錄/`](document/架構重整/02_決策與退役執行記錄/) 的 Work Package／驗收記錄與 [`03_追蹤清單與證據/`](document/架構重整/03_追蹤清單與證據/) 的 evidence，需依各自 declared status 解讀。

規格與現況不一致時，必須明確揭露漂移；不得以程式目前能執行為由覆蓋已確認的業務語意。

## 協作與交付

- 開始前讀取 branch、HEAD、status 與相鄰檔案；現有未提交變更屬於使用者成果。
- 只修改本次任務直接需要的檔案；不要 reset、clean、stash、切換分支或順便重構。
- 以名稱、型別、短函式與 guard clause 表達意圖；Streamlit 永遠是可替換的薄顯示層。
- 修改 API、資料模型、業務規則、migration 或外部副作用時，同步更新相應的規格、決策或 evidence 索引。
- 未經明確要求，不得自行 stage、commit、push 或建立 PR。
