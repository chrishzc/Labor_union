# Global Deployment 與治理正式規格

## 1. 文件狀態與裁決

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- Logical deployment topology：`consolidated-decision`
- 建議 production profile：`local-primary`（`recommended-candidate`）
- Tunnel／edge vendor、RTO／RPO 與營運責任：`human-decision-required`
- ADAD／Checkpoint／Source Lock／system map gate：`historical`
- 當前核准只啟用 Inventory v2 evidence；本文件 migration、deployment、release、
  pytest 與 recovery contract 不授權本輪執行任何 mutation。

本文件固定安全邊界、release state machine 與人工批准點；不把單一廠商或機器名稱
寫成業務 Domain 依賴。

## 2. Global Deployment 不變量

1. MySQL 只存在於 private data zone，不公開 Port 3306。
2. public edge 只暴露必要 HTTPS endpoint；管理後台預設只允許 LAN／VPN／受控 access。
3. TLS 在受管理的 edge／reverse proxy 終止，edge 到 application 的信任邊界必須明確。
4. production 禁止 ngrok；`start_fastapi_ngrok.py` 只屬 development tool。
5. FastAPI、Worker、Streamlit、File Watcher 與 migration runner 使用最小權限、
   分離 credential 與明確 health check。
6. File Watcher 只建立 durable ingestion job，不直接正式入帳或改 Domain 狀態。
7. production secret 不進 Git、文件、log、process argument、UI 或 migration receipt。
8. 所有 schema 變更走 preserve-data release manifest、backup、candidate、validation、
   config switch、restart/read-smoke 與 recovery receipt。
9. release 未通過 post-start verification 時不得標示完成。
10. 部署位置變更不得改變 Domain ownership、API contract、transaction 或資料語意。

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
                    │ private authenticated connection
      ┌─────────────┴─────────────┐
      │         Data Zone          │
      │ MySQL / Archive / Backup   │
      └────────────────────────────┘
```

### 3.1 Public Edge

允許：

- LINE webhook；
- BreezySign webhook；
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

正式傳輸目標為 HTTP/2；HTTP/1.1 是相容 fallback，HTTP/3 是可選優化，不得成為
正確性或可用性的唯一前提。JSON／text 可以依共同效能契約壓縮，XLSX、圖片及已壓縮
artifact 不得重複壓縮。

### 3.2 Application Zone

- FastAPI：唯一正式 HTTP business／integration boundary。
- Worker：消費 committed outbox、LINE task、durable inbox 與 anomaly scan。
- Streamlit：薄 Presentation Adapter，只呼叫 FastAPI。
- File Watcher：偵測來源檔並建立 durable import job；不持有正式 ledger writer。
- Migration Runner：只在 maintenance window、專用 principal 與 maintenance token 下啟用。

各 process 必須可獨立 restart；background worker failure 不得隱藏在 API health 200。

### 3.3 Data／Archive Zone

- MySQL schema 使用 application、worker、migration、read-only rehearsal 等分離 principal。
- XLSX archive、evidence archive、DB backup 都保存 digest 與 retention metadata。
- archive failure 不得使匯出／release receipt宣稱完整。
- backup 必須可 restore 驗證；「檔案存在」不是可復原證據。

## 4. Deployment profiles

### 4.1 `local-primary`（建議候選 profile）

- FastAPI、Worker、Streamlit、File Watcher 在工會受管主機執行。
- MySQL 位於同一受控網段或地端 NAS private network。
- public webhook 經 managed HTTPS tunnel／edge 進入 FastAPI。
- 管理 UI 只經 LAN／VPN 或同等受控入口。
- 主機必須具備 service supervision、開機自啟、UPS／停電處置與遠端維護路徑。

此 profile 是基於目前地端運作目標提出的候選，不因 `online.bat` 現況而自動生效。
只有人工完成 deployment decision record 並通過 24/7、health、secret、recovery
與責任歸屬驗證後，才能成為 target profile。

### 4.2 `hybrid-app-host`（候選 profile）

- FastAPI、Worker、Streamlit 可移至受管 cloud host。
- MySQL 維持 private data zone，僅以 VPN／private network 連接。
- cloud host 不保存長期 DB backup 或未加密敏感資料。
- DB latency、VPN partition、credential rotation、data egress 與 incident ownership
  必須在採用前完成 Global E2E。

切換 profile 是 architecture／security／operations 變更，必須人工重新確認，
不能只改環境變數。

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
- target deployment profile；
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
- public edge／private admin edge；
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

上線前必須補入正式 deployment decision record：

1. public edge／tunnel provider、domain 與 certificate owner；
2. 管理端 private access 方法；
3. RTO、RPO、backup interval、retention 與 restore rehearsal interval；
4. maintenance window、primary operator、approver 與 incident contact；
5. service host／NAS／UPS／VPN ownership；
6. production secret store 與 rotation interval；
7. `local-primary` 是否達到 24/7 availability；若否，是否切換 `hybrid-app-host`。

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
- deployment profile／security boundary；
- production DB、credentials、network 或 external platform side effect；
- Work Package scope 擴大。

只有未來 Work Package 明載 production／pytest write set 時，才可在該已確認範圍內
自主完成：

- Module 實作與相應測試；
- 不改 contract 的 bug fix；
- 同 scope failure repair；
- deterministic formatting／generated artifact sync；
- read-only verification。

## 10. Legacy 文件處理

- `document/文件整併工作區` 保留為來源與追溯，不再使用 ADAD 授權語彙。
- `system_map*.md`／`system_map*.yaml` 只供歷史比對。
- `start_fastapi_ngrok.py` 只屬 development。
- `online.bat`／`start.bat` 是 live operational evidence，不自動成為 deployment SSOT。
- `04_部署架構_無損合併稿.md` 的方案比較保留，但本文件的 logical topology、
  profile recommended-candidate 與人工選擇規則優先。

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
- `local-primary` 斷電、網路中斷、worker crash 與 backup restore演練；
- profile switch 不改 Domain behavior。

## 12. 來源追溯

- `08_ADAD卸載與Legacy資料邊界.md`
- `10_Global_保留資料Migration與Cutover_Subsystem.md`
- `12_Global_效能與UX體感架構.md`
- `document/文件整併工作區/04_部署架構_無損合併稿.md`
- `README.md`
- `start.bat`
- `online.bat`
- `start_fastapi_ngrok.py`
- `scripts/bootstrap_admin_dev_env.ps1`
- 根目錄 `AGENTS.md`

live 啟動腳本僅作現況證據；正式 release 仍須依本文件 manifest 與 gate 驗證。
