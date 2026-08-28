# Global Deployment 與治理正式規格

## 1. 文件狀態與裁決

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- API-only DB runtime 補充裁決：`approved-by-user-2026-08-14`
- Cloud-ready runtime supervision 補充裁決：`approved-by-user-2026-08-14`
- Logical deployment topology：`consolidated-decision`
- Deployment profile／target-host acceptance：`retired-by-user-2026-08-09`
- ADAD／Checkpoint／Source Lock／system map gate：`historical`
- 2026-08-26 人工已核准 Cloud／worker／alert sink qualification、部署計畫、隔離環境 rehearsal
  與 rollback 準備；先前「只啟用 Inventory v2 evidence」的本輪限制由本項 supersede。
- 這項核准不恢復已退役的 deployment profile／target-host application gate，也不直接授權猜測
  production／`union_db` 目標、外部 deployment、entry switch 或不可逆 cutover。實際外部執行前仍須
  回讀 exact environment、host／project、credential class、operator、budget／quota、maintenance window、
  backup／rollback 與 readback，並由涵蓋該精確 target 的 Work Package 進入 `execution_approved`。

本文件固定安全邊界、release state machine 與人工批准點；不把單一廠商或機器名稱
寫成業務 Domain 依賴。

## 2. Global Deployment 不變量

1. MySQL 只存在於 private data zone，不公開 Port 3306。
2. public edge 只暴露必要 HTTPS endpoint；管理後台預設只允許 LAN／VPN／受控 access。
3. TLS 在受管理的 edge／reverse proxy 終止，edge 到 application 的信任邊界必須明確。
4. production 禁止 ngrok；`scripts/launchers/start_fastapi_ngrok.py` 只屬 development tool。
5. FastAPI、Worker、Streamlit、File Watcher 與 migration runner 使用最小權限、
   分離 credential 與明確 health check；Worker／Monitor 不持有 DB credential。
6. File Watcher 只建立 durable ingestion job，不直接正式入帳或改 Domain 狀態。
7. production secret 不進 Git、文件、log、process argument、UI 或 migration receipt。
8. 所有 schema 變更走 preserve-data release manifest、backup、candidate、validation、
   config switch、restart/read-smoke 與 recovery receipt。
9. release 未通過 post-start verification 時不得標示完成。
10. 部署位置變更不得改變 Domain ownership、API contract、transaction 或資料語意。
11. Private Operations API 的 production caller 必須使用 Google-signed OIDC ID token；audience、
    issuer 與 service-account caller allowlist 必須精確驗證，local shared key 禁止 fallback 到 production。
12. Worker heartbeat 必須記錄 authenticated caller 的 runtime identity，不得以 FastAPI process 的
    PID、hostname 或 instance identity 冒充 Worker。

## 3. Logical topology

```text
External Platforms / Approved Admin Client
                    │
             HTTPS Public/Private Edge
                    │
      ┌─────────────┴─────────────┐
      │       Application Zone     │
      │ FastAPI / Worker / UI /    │
      │ Durable Ingestion Producer │
      └─────────────┬─────────────┘
                    │ FastAPI-only private authenticated DB connection
      ┌─────────────┴─────────────┐
      │         Data Zone          │
      │ MySQL / Archive / Backup   │
      └────────────────────────────┘
```

### 3.1 Public Edge

允許：

- LINE webhook；
- LIFF callback／必要 public read endpoint；
- health endpoint 的最小非敏感資訊。

禁止：

- MySQL；
- Data Browser；
- administrator mutation API 的未受控公網存取；
- debug endpoint；
- dev tunnel inspection；
- raw backup／archive。

Edge 必須提供 TLS、request size limit、timeout、rate limit、source／signature validation
支援與 request correlation。

HTTP/1.1 request／response 相容性是 application transport contract；HTTP/2、HTTP/3 與
connection reuse 都是部署者可選的外部優化，不得成為正確性、可用性或 release 的唯一前提。
JSON／text 可以依共同效能契約壓縮，XLSX、圖片及已壓縮 artifact 不得重複壓縮。

### 3.2 Application Zone

- FastAPI：唯一正式 HTTP business／integration boundary。
- Worker：透過 authenticated Private Operations API 觸發 committed outbox、LINE task、durable
  inbox 與 anomaly scan 的完整一次性 operation；不得直接連 MySQL。
- Streamlit：薄 Presentation Adapter，只呼叫 FastAPI。
- File Watcher：偵測來源檔並建立 durable import job；不持有正式 ledger writer。
- Migration Runner：只在 maintenance window、專用 principal 與 maintenance token 下啟用。

各 process 必須可獨立 restart；background worker failure 不得隱藏在 API health 200。FastAPI
lifespan 禁止內嵌啟動 background worker；同一 operation 不得因 API instance 數量而重複建立 thread。

Private operation endpoint 必須固定允許的 caller service。Worker／Monitor 自報 service name 只作
request binding，不能取代已驗證的 OIDC identity。local/test 可使用至少 32 字元 shared key；production
只接受精確 audience 與 allowlist 通過的短效 OIDC token，缺少任一設定時 fail closed。

### 3.3 Data／Archive Zone

- MySQL schema 使用 application、migration、read-only rehearsal 等分離 principal；runtime production
  connection 只有 FastAPI application composition 可取得。Worker／Monitor 只能持有 service identity，
  經 Private Operations API 間接執行既有 transaction。
- XLSX archive、evidence archive、DB backup 都保存 digest 與 retention metadata。
- archive failure 不得使匯出／release receipt宣稱完整。
- backup 必須可 restore 驗證；「檔案存在」不是可復原證據。

## 4. Deployment boundary

本系統不保存 deployment profile、target host、edge vendor、RTO/RPO 或 host ownership
設定，也不以 target-host acceptance 作為程式 release gate。這些是部署者的外部作業選擇，
不得寫入 application config、schema、API 或 UI。第 2 節的資料庫私網、HTTPS、secret
不入 Git 與 preserve-data release 安全不變量仍然有效。

2026-08-26 current execution authorization 允許在上述邊界內完成 deployment source inventory、
isolated qualification、preflight、rehearsal 與 rollback plan；它是施工與驗收授權，不是 production
target fact，也不能建立或填補 deployment profile。任何外部 mutation 都必須在執行當下以精確 target
與 receipt 證明，未解析 target 固定 fail closed。

## 5. Subsystem：Release Orchestration

### 5.1 State machine

```text
prepared
  → preflight_passed
  → awaiting_execution_approval
  → execution_approved
  → backup_verified
  → candidate_created_or_restored
  → candidate_schema_applied
  → candidate_backfill_verified
  → candidate_data_validated
  → candidate_validated
  → awaiting_release_approval
  → release_approved
  → switched
  → restart_verified
  → released

任一步驟 → failed
switched 後失敗 → recovery_required → recovered | escalated
```

### 5.2 Release manifest

Manifest 至少包含：

- release version；
- Git commit／artifact digest；
- schema release manifest digest；
- application config schema version；
- required secrets 的名稱，不含值；
- source／candidate database identity；
- backup receipt；
- operator、maintenance window、correlation ID；
- architecture package identity 與人工 architecture approval receipt；
- execution approval receipt：本 Work Package 可建立 backup／candidate 的 exact target、
  allowed mutation scope、operator、granted time 與 expires time；
- release approval receipt：approver、approval scope、artifact／schema／profile digest、
  granted time、expires time 與 correlation identity；
- 若本次包含已明載且允許的 external side effect，另附 scope-bound
  external-side-effect approval receipt；
- health／smoke／rollback commands 的 versioned contract。

### 5.3 Preflight

Fail closed 檢查：

- production environment identity；
- required secret；
- DB host／schema／principal；
- pending migration／schema drift；
- backup target 可寫與 restore 工具可用；
- port collision；
- worker／API／UI version一致；
- legacy writer inventory release threshold；
- uncommitted／unversioned artifact 不得作正式 release。
- 缺 scope-bound execution approval 不得建立 backup／candidate 或執行 migration。
- release approval 的 scope、digest、profile 或有效期任一不符，不得 switch。
- candidate create／restore、schema apply、backfill、data validation 每一段都必須有
  durable journal receipt，不得以單一 `candidate_validated` 跳過。

### 5.4 Switch／Recovery

- configuration switch 必須原子且留下 before／after receipt。
- restart/read-smoke 是 switch 後獨立 gate。
- 一般 rollback 是原子切回 immutable original source identity，再 restart／read-smoke；
  candidate 保留供鑑識，不得刪除或原地修補 source。
- backup restore 只能還原到新的 recovery candidate，禁止原地覆寫 source 或既有
  candidate；它是獨立 recovery Work Package，必須驗證 exact new target、backup
  digest、restore drill 與人工 external-side-effect approval。
- 本 package 禁止不可逆／破壞式 migration；人工 release approval 不能覆蓋此不變量。
  若業務未來確需不可逆操作，必須先建立新的 architecture／data-migration 規格。
- 任何 recovery failure 立即 `escalated`，不得以部分服務可用宣稱 released。

`degraded` 只可描述「先前已成功 release 後」的 runtime operational state，並列出
capability matrix、owner 與 recovery action；本次 release gate 有任一必需 capability
不健康時，整體 release 失敗，不得以 partial release 取代。

## 6. Subsystem：Runtime Supervision／Observability

必須分別觀測：

- FastAPI readiness／liveness；
- Worker heartbeat、queue lag、retry／dead-letter；
- durable inbox oldest pending；
- MySQL connectivity、transaction latency、pool saturation；
- Streamlit→API error rate；
- public edge availability、TLS expiry、signature failure；
- protocol negotiation、compression ratio、first-byte 與 end-to-end latency；
- File Watcher durable job creation；
- backup age、restore rehearsal age；
- disk／archive capacity。

Monitor process 只觀測其真正可見的 API／UI／public edge／LIFF transport。MySQL、Redis、queue 與
media storage 必須由 FastAPI application composition 使用同一份 runtime 設定探測；不得讓外部
Monitor 以預設值或不同 mount path 產生假健康或假故障。`/health` 只代表 process liveness，DB-aware
dependency readiness 由 authenticated Private Operations API 提供。

依 `00` §2.2，受控檔案 storage 的正式 runtime target 是工會地端 NAS mount。application、watcher、
worker 與 backup job 必須使用同一個受控 storage configuration／logical root；不得把 host 路徑、UNC
位置或 container 內暫存路徑寫入 public metadata。readiness 至少區分 mount unavailable、read denied、
capacity exhausted、watcher lag、digest mismatch 與 metadata/object orphan；只有實際掛載該 NAS 的地端
作業環境可直接操作資料夾。未掛載 NAS 的 Web／LIFF consumer 只能透過 authenticated list／download／
versioned upload contract 存取，不能退回本機預設資料夾或顯示假健康。

Controlled-file runtime status（2026-08-26）：本機 storage composition、typed API 與 Data Center adapter
已接線，`lu_test_*` fresh／preserve-data metadata release 驗收為 `passed`；正式 NAS mount、capacity／watcher
運維、backup／restore drill、production deployment 與 entry switch 均未執行。local-bypass 對受保護 route
回 403 是預期負向控制，不得當作 enabled human authenticated acceptance。

Private Operations client 必須依 typed `retryable` 決定是否重試；HTTP status 只能作缺少 typed
envelope 時的保守 fallback。transient retry 必須有上限、exponential backoff 與 jitter；認證、設定、
schema 或 contract failure 不得無限重試。一次性 CLI cycle 只要未成功即回傳非零。

Logs 必須具 correlation ID、service、release version、operation 與 typed error code；
禁止記錄 session token、internal key、bank account、raw webhook secret 或完整個資 payload。

## 7. Typed deployment errors

| Code | Release 行為 |
|---|---|
| `deployment_preflight_failed` | 不開始 mutation |
| `deployment_secret_missing` | fail closed |
| `deployment_identity_mismatch` | fail closed／人工確認 |
| `database_unreachable` | 不切換 |
| `migration_drift_detected` | 不 Apply |
| `backup_unverified` | 不 Apply |
| `candidate_validation_failed` | 不切換 |
| `public_edge_unhealthy` | 整體 release 失敗；所有 component 都不得標示本 package 已 released |
| `worker_not_ready` | 不宣稱完整 release |
| `post_restart_smoke_failed` | recovery_required |
| `recovery_failed` | escalated |

## 8. Human-decision-required

無。deployment profile 與 target-host acceptance 已退出正式產品設定；外部部署者不得藉此
改變第 2 節的安全不變量或 Domain 行為。

## 9. 現行治理模型

### 9.1 正式流程

```text
來源與 live evidence
  → Global／Domain／Subsystem／Module 架構提案
  → 人工整體架構確認
  → Work Package（scope、write set、acceptance、side effects）
  → production code／分層 pytest
  → evidence matrix／獨立核對
  → 人工 release／external-side-effect approval
  → deployment／migration
  → post-start verification／release receipt
  → 不再 active 的執行文件通過 archive gate 後低頻封存
```

目前 activation 只到 `Writer Inventory v2` 的唯讀盤點、語意分類、digest 與 evidence
artifact；不得自動進入 production code、pytest、migration、release 或 deployment。

### 9.2 語彙替換

| 過期語彙 | 正式語彙 |
|---|---|
| ADAD Task | Work Package |
| CP-1／Checkpoint-1 | 人工整體架構確認 |
| CP-2／Checkpoint-2 | 人工 release／external-side-effect approval |
| Source Lock | Work Package 明確 write scope 與 ownership |
| Task snapshot | Work Package status／evidence record |
| system map gate | 正式架構文件＋live evidence matrix |
| ADAD Reviewer | 分層測試＋獨立核對者 |
| transition gate | 明確 acceptance／release gate |

禁止把 legacy 名詞做字面替換後繼續引用舊授權。舊 Task、Checkpoint、Lock、
system map 都不具現行 authority。

### 9.3 Change control

必須停止並重新取得人工確認：

- Global／Domain ownership；
- root fact／derived value；
- state machine／transaction boundary；
- data contract／public API；
- schema destructive change；
- security boundary；
- production DB、credentials、network 或 external platform side effect；
- Work Package scope 擴大。

只有未來 Work Package 明載 production／pytest write set 時，才可在該已確認範圍內
自主完成：

- Module 實作與相應測試；
- 不改 contract 的 bug fix；
- 同 scope failure repair；
- deterministic formatting／generated artifact sync；
- read-only verification。

## 10. Legacy 與已完成文件處理

- `document/文件整併工作區` 保留為來源與追溯，不再使用 ADAD 授權語彙。
- `system_map*.md`／`system_map*.yaml` 只供歷史比對。
- `scripts/launchers/start_fastapi_ngrok.py` 只屬 development。
- `scripts/launchers/start_local_development.bat`／`.sh` 是本機開發 launcher，不得用於 production
  deployment，也不構成 deployment SSOT；舊 `online.bat`／`online.sh` 已搬移，重複的 `start.bat`
  已退役。
- operator-facing launcher 集中在 `scripts/launchers/`；實際 worker／monitor process module 留在
  `scripts/`，不得因目錄收斂改變 owner、交易或 external side-effect 契約。
- Windows／Unix 本機 launcher 都必須在啟動服務前執行 current schema readiness，並以唯讀 preflight
  決定 optional LINE／Knowledge workers。DB update preview 的 `blocked` 必須回傳非零 exit code；只有
  與 latest release identity／fingerprint 完全相符的 qualification receipt 可解鎖 additive execution。
- `04_部署架構_無損合併稿.md` 的方案比較保留，但本文件的 logical topology、
  profile recommended-candidate 與人工選擇規則優先。

### 10.1 Current SSOT 與低頻封存

- `01_規格基線/` 只保存仍約束 current production 的精簡正式規格；完成實作或上線不會降低
  規格權威，也不是搬入 archive 的理由。
- `02_決策與退役執行記錄/` 與 `03_追蹤清單與證據/` 優先保存 active、blocked、awaiting
  execution／release、current recovery 與最近驗收所需文件。
- `04_已完成與上線封存/` 保存不再 active 的 completed Work Package、已有 successor 的
  superseded 舊規格，以及 closed release／receipt。其內容不是 current SSOT 或新 mutation 授權。
- Agent 日常開工禁止遞迴讀取 archive；只有歷史追溯、incident／rollback、migration/cutover、
  舊 release 重現、稽核或 current SSOT 明確引用時，才精準搜尋 manifest 並讀單一文件。

### 10.2 Archive gate

搬移前必須同時具備 final status、completion evidence、deployment/release identity（如適用）、
current successor（如適用）、完整 inbound-link 更新、content SHA-256、archive manifest entry 與
restore triggers。仍有 blocker、待辦、人工操作入口、rollback 責任或 awaiting execution 的文件
不得封存。無法唯一判定時留在原位並進人工 review，不得自動搬移或刪除。

封存後 active index 只保留一行 archive pointer 或分類摘要；不得以減少上下文為由刪除 Git
history、validation assets、release artifacts 或 current recovery evidence。

## 11. 分層驗收

### Module

- manifest、config schema、secret presence、health parser、log redaction。

### Subsystem

- preflight fail closed；
- backup／candidate／switch／restart receipts；
- worker/API/UI partial failure；
- recovery replay；
- edge／VPN／DB partition。

### Global

- disposable environment 完整 release 與 recovery rehearsal；
- production-like edge＋TLS＋signature；
- DB 不暴露公網；
- release artifact全部有 commit／digest；
- worker crash 與 backup restore 的 disposable contract 演練。

## 12. 來源追溯

- 根目錄 `AGENTS.md` 的 ADAD／legacy 邊界規則
- `10_Global_保留資料Migration與Cutover_Subsystem.md`
- `12_Global_效能與UX體感架構.md`
- `document/文件整併工作區/04_部署架構_無損合併稿.md`
- `README.md`
- `scripts/launchers/README.md`
- `scripts/launchers/start_local_development.bat`
- `scripts/launchers/start_local_development.sh`
- `scripts/launchers/start_fastapi_ngrok.py`
- `scripts/launchers/configure_local_admin_no_auth.ps1`
- `../04_已完成與上線封存/release_records/53_Deployment_Profile_and_Target_Host_Acceptance_Retirement.md`
- 根目錄 `AGENTS.md`

live 啟動腳本僅作現況證據；正式 release 仍須依本文件 preserve-data manifest 驗證，
不得要求 deployment profile 或 target-host acceptance。
